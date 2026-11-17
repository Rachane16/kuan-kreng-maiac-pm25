"""Aggregate 24 hourly CAMS AOD values by Thai day and clip native cells."""
from __future__ import annotations

import json
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
from netCDF4 import Dataset, num2date
from shapely.geometry import box, mapping

THAI = ZoneInfo("Asia/Bangkok")


def read_hours(paths: list[Path]) -> tuple[np.ndarray, np.ndarray, dict]:
    records = {}
    latitude = longitude = None
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".nc"):
                    continue
                with Dataset("cams.nc", memory=archive.read(name)) as ds:
                    if "aod550" not in ds.variables:
                        continue
                    lat = np.asarray(ds["latitude"][:], dtype=float)
                    lon = np.asarray(ds["longitude"][:], dtype=float)
                    if latitude is not None and (not np.array_equal(lat, latitude) or not np.array_equal(lon, longitude)):
                        raise ValueError("CAMS input grid changed")
                    latitude, longitude = lat, lon
                    field = ds["aod550"]
                    axes = [field.dimensions.index(n) for n in
                            ("forecast_reference_time", "forecast_period", "latitude", "longitude")]
                    values = np.ma.filled(field[:], np.nan).astype(float).transpose(axes)
                    tv = ds["valid_time"]
                    times = num2date(tv[:], tv.units, only_use_cftime_datetimes=False,
                                     only_use_python_datetimes=True)
                    times = np.asarray(times).transpose([tv.dimensions.index(n) for n in
                                                        ("forecast_reference_time", "forecast_period")])
                    rv = ds["forecast_reference_time"]
                    references = num2date(rv[:], rv.units, only_use_cftime_datetimes=False,
                                          only_use_python_datetimes=True)
                    leads = np.asarray(ds["forecast_period"][:], dtype=float)
                    if values.shape[:2] != times.shape:
                        raise ValueError("CAMS time dimensions do not match values")
                    for r, base in enumerate(references):
                        for h, lead in enumerate(leads):
                            valid = times[r, h].replace(tzinfo=timezone.utc)
                            base_utc = base.replace(tzinfo=timezone.utc)
                            if valid != base_utc+timedelta(hours=float(lead)):
                                raise ValueError("CAMS valid time differs from reference plus lead")
                            key = valid.isoformat()
                            item = (valid, base_utc, int(lead), values[r, h])
                            if key in records and not np.allclose(records[key][3], values[r, h], equal_nan=True):
                                raise ValueError("Conflicting CAMS values at the same valid time")
                            records[key] = item
    if latitude is None or longitude is None or not records:
        raise ValueError("No CAMS AOD550 data in input")
    return latitude, longitude, records


def native_grid(latitude: np.ndarray, longitude: np.ndarray, boundary_path: Path) -> gpd.GeoDataFrame:
    if len(latitude)<2 or len(longitude)<2:
        raise ValueError("At least two native centres per axis are needed to verify spacing")
    dy = float(np.median(np.abs(np.diff(latitude))))
    dx = float(np.median(np.abs(np.diff(longitude))))
    if not (np.allclose(np.abs(np.diff(latitude)), .4) and np.allclose(np.abs(np.diff(longitude)), .4)):
        raise ValueError("Expected the ADS native 0.4 degree grid")
    boundary = gpd.read_file(boundary_path).to_crs(4326).geometry.union_all()
    rows = []
    for i, lat in enumerate(latitude):
        for j, lon in enumerate(longitude):
            geometry = box(lon-dx/2, lat-dy/2, lon+dx/2, lat+dy/2).intersection(boundary)
            if not geometry.is_empty and geometry.area>0:
                rows.append({"grid_id": f"CAMS_{lat:.1f}_{lon:.1f}", "row": i, "col": j,
                             "latitude": float(lat), "longitude": float(lon), "geometry": geometry})
    grid = gpd.GeoDataFrame(rows, crs=4326)
    if grid.empty:
        raise ValueError("CAMS grid does not intersect the study boundary")
    grid["overlap_m2"] = grid.to_crs(32647).area
    return grid


def daily_record(day: date, hours: dict, grid: gpd.GeoDataFrame, model) -> dict:
    start = datetime.combine(day, time.min, THAI).astimezone(timezone.utc)
    end = start+timedelta(days=1)
    wanted = [start+timedelta(hours=h) for h in range(24)]
    entries = [hours.get(t.isoformat()) for t in wanted]
    record = {"date": day.isoformat(), "status": "NotPublished", "available_cells": 0,
              "mean_pm25": None, "cells": [], "period_start_utc": start.isoformat(),
              "period_end_utc": end.isoformat(), "forecast_base_time": None,
              "lead_time_hours": None, "available_hours": sum(e is not None for e in entries)}
    if not all(e is not None for e in entries):
        if record["available_hours"]:
            record["status"] = "Incomplete"
        return record
    bases = {e[1] for e in entries}
    if len(bases) != 1:
        raise ValueError("A Thai daily record must use one forecast reference cycle")
    record["forecast_base_time"] = entries[0][1].isoformat()
    record["lead_time_hours"] = [min(e[2] for e in entries), max(e[2] for e in entries)]
    aod = np.stack([e[3] for e in entries])
    cells, features = [], []
    for row in grid.itertuples():
        values = aod[:, row.row, row.col]
        # Never turn a partial day or negative/missing AOD into a complete daily estimate.
        if not (np.isfinite(values).all() and (values>=0).all()):
            continue
        mean = float(values.mean())
        cells.append([row.grid_id, mean, None, 24])
        features.append(mean)
    if cells:
        predictions = model.predict(pd.DataFrame({"AOD 0.47": features}))
        weights = dict(zip(grid.grid_id, grid.overlap_m2))
        record["mean_pm25"] = round(float(np.average(predictions, weights=[weights[c[0]] for c in cells])), 2)
        for cell, prediction in zip(cells, predictions):
            cell[1], cell[2] = round(cell[1], 5), round(float(prediction), 2)
    record.update(status="Available" if cells else "NoData", cells=cells, available_cells=len(cells))
    return record


def export(paths: list[Path], start: date, end: date, boundary: Path, model_path: Path,
           site_data: Path, merge: bool = True) -> Path:
    lat, lon, hours = read_hours(paths)
    grid = native_grid(lat, lon, boundary)
    model = joblib.load(model_path)
    if list(getattr(model, "feature_names_in_", [])) != ["AOD 0.47"]:
        raise ValueError("Model feature names differ from the trusted original model")
    site_data.mkdir(parents=True, exist_ok=True)
    history_path = site_data/"cams_history.json"
    previous = json.loads(history_path.read_text(encoding="utf-8")) if merge and history_path.exists() else {}
    days = {d["date"]:d for d in previous.get("days", [])}
    current = start
    while current<=end:
        record = daily_record(current, hours, grid, model)
        # A recent-only download must preserve previously checked historical dates.
        if record["available_hours"] or current.isoformat() not in days:
            days[current.isoformat()] = record
        current += timedelta(days=1)
    history = {"source": "CAMS AOD550 / Extra Trees", "time_zone": "Asia/Bangkok",
               "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "start_date": start.isoformat(), "end_date": end.isoformat(),
               "grid_count": len(grid), "resolution_degrees": .4, "aod_wavelength_nm": 550,
               "aggregation": "mean of 24 hourly AOD550 values in the Thai calendar day, followed by Extra Trees prediction",
               "forecast_cycle": "12:00 UTC of the preceding day, lead hours 5 through 28",
               "model": model_path.name, "days": [days[(start+timedelta(days=n)).isoformat()] for n in range((end-start).days+1)]}
    features = [{"type":"Feature", "properties":{
        "grid_id":row.grid_id, "latitude":row.latitude, "longitude":row.longitude,
        "overlap_m2":round(row.overlap_m2, 2), "resolution_degrees":.4},
        "geometry":mapping(row.geometry)} for row in grid.itertuples()]
    (site_data/"cams_grid.geojson").write_text(json.dumps({"type":"FeatureCollection", "features":features},ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    history_path.write_text(json.dumps(history,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    print(f"CAMS exported {len(history['days'])} Thai days, {len(grid)} clipped native cells",flush=True)
    return history_path
