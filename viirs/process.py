"""QA-filter native swath samples, then aggregate on a clipped 6 km reporting grid."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import numpy as np
import pandas as pd
from netCDF4 import Dataset
from pyproj import Transformer
from shapely import intersects_xy
from shapely.geometry import box, mapping

THAI = ZoneInfo("Asia/Bangkok")
STEP = 6000


def grid_id(x, y):
    return f"VIIRS_E{int(np.floor(x/STEP))*STEP}_N{int(np.floor(y/STEP))*STEP}"


def reporting_grid(boundary_path):
    frame = gpd.read_file(boundary_path)
    if frame.crs is None or frame.empty:
        raise ValueError("Missing study boundary/CRS")
    boundary = frame.to_crs(32647).geometry.union_all()
    west, south, east, north = boundary.bounds
    if not (0 < east-west < 200000 and 0 < north-south < 200000):
        raise ValueError("VIIRS processing is restricted to the local study area")
    rows = []
    for x in range(int(np.floor(west/STEP))*STEP, int(east)+STEP, STEP):
        for y in range(int(np.floor(south/STEP))*STEP, int(north)+STEP, STEP):
            shape = boundary.intersection(box(x, y, x+STEP, y+STEP))
            if not shape.is_empty and shape.area > 0:
                rows.append({"grid_id": grid_id(x, y), "overlap_m2": shape.area,
                             "reporting_grid_m": STEP, "native_resolution_km_at_nadir": 6,
                             "geometry": shape})
    grid = gpd.GeoDataFrame(rows, crs=32647).to_crs(4326)
    return grid, boundary


def quality_mask(aod, qa, lat, lon):
    if not (aod.shape == qa.shape == lat.shape == lon.shape):
        raise ValueError("VIIRS AOD/QA/geolocation dimensions differ")
    return (np.isfinite(aod) & (aod >= 0) & (aod <= 5) & np.isin(qa, [2, 3])
            & np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180))


def variables(dataset):
    result = dict(dataset.variables)
    for group in dataset.groups.values():
        for name, value in variables(group).items():
            if name not in result:
                result[name] = value
    return result


def samples(path, boundary):
    with Dataset(str(path)) as source:
        fields = variables(source)
        names = ("Aerosol_Optical_Thickness_550_Land_Best_Estimate",
                 "Aerosol_Optical_Thickness_QA_Flag_Land", "Latitude", "Longitude")
        if any(name not in fields for name in names):
            raise ValueError("VIIRS Deep Blue land AOD550/QA/geolocation layers missing")
        aod, qa, lat, lon = [np.ma.filled(np.ma.asarray(fields[name][:], dtype=float), np.nan) for name in names]
    mask = quality_mask(aod, qa, lat, lon)
    transform = Transformer.from_crs(4326, 32647, always_xy=True)
    x, y = transform.transform(lon[mask], lat[mask])
    values = aod[mask]
    inside = intersects_xy(boundary, x, y)
    return [(grid_id(px, py), float(value)) for px, py, value in zip(np.asarray(x)[inside], np.asarray(y)[inside], values[inside])]


def daily_record(day, readings, grid, model, granules):
    start = datetime.combine(day, time.min, THAI).astimezone(timezone.utc)
    groups = {}
    valid_ids = set(grid.grid_id)
    for key, value in readings:
        if key in valid_ids and np.isfinite(value) and value >= 0:
            groups.setdefault(key, []).append(value)
    keys = sorted(groups)
    means = [float(np.mean(groups[key])) for key in keys]
    predictions = np.asarray(model.predict(pd.DataFrame({"AOD 0.47": means})), dtype=float) if means else np.array([])
    if len(predictions) != len(keys) or not np.isfinite(predictions).all() or (predictions < 0).any():
        raise ValueError("Trusted Extra Trees returned invalid predictions")
    weights = dict(zip(grid.grid_id, grid.overlap_m2))
    cells = [[key, round(aod, 6), round(float(pm), 2), len(groups[key])]
             for key, aod, pm in zip(keys, means, predictions)]
    support = sum(weights[key] for key in keys)/sum(weights.values())
    return {"date": day.isoformat(), "status": "Available" if cells else "NoData",
            "available_cells": len(cells), "cells": cells,
            "mean_pm25": round(float(np.average(predictions, weights=[weights[key] for key in keys])), 2) if cells else None,
            "coverage_fraction": round(support, 6), "valid_pixels": sum(map(len, groups.values())),
            "period_start_utc": start.isoformat(), "period_end_utc": (start+timedelta(days=1)).isoformat(),
            "satellites": sorted({item["satellite"] for item in granules}),
            "observation_times_utc": sorted({item["time_start"] for item in granules}),
            "input_granules": granules}


def grid_geojson(grid):
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {
        "grid_id": row.grid_id, "overlap_m2": round(row.overlap_m2, 3), "reporting_grid_m": STEP,
        "native_resolution_km_at_nadir": 6}, "geometry": mapping(row.geometry)} for row in grid.itertuples()]}
