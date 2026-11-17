"""Publish a single available CAMS cycle at hourly valid times (0–120 h)."""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone, date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .fetch import COLLECTION, URL, download_request, request_for_days
from .process import native_grid, read_hours


def latest_cycle(constraints: list[dict], now: datetime) -> datetime:
    """Use ADS availability, never assume a not-yet-published 00/12 UTC run."""
    candidates = set()
    rows = [r for r in constraints if "total_aerosol_optical_depth_550nm" in r.get("variable", [])
            and "forecast" in r.get("type", [])]
    for row in rows:
        for interval in row.get("date", []):
            ends = interval.split("/")
            first, last = date.fromisoformat(ends[0]), date.fromisoformat(ends[-1])
            last = min(last, now.date())
            if last < first:
                continue
            for hour in ("00:00", "12:00"):
                if hour in row.get("time", []):
                    candidate = datetime.combine(last, time.fromisoformat(hour), timezone.utc)
                    if candidate > now:
                        candidate -= timedelta(days=1)
                    if candidate.date() >= first:
                        candidates.add(candidate)
    for candidate in sorted(candidates, reverse=True):
        leads = set()
        for row in rows:
            if candidate.strftime("%H:%M") not in row.get("time", []):
                continue
            for interval in row.get("date", []):
                ends = interval.split("/")
                if date.fromisoformat(ends[0]) <= candidate.date() <= date.fromisoformat(ends[-1]):
                    # ADS separates 6-hourly steps and intermediate hours into different rows.
                    leads.update(row.get("leadtime_hour", []))
        if set(map(str, range(121))).issubset(leads):
            return candidate
    raise ValueError("ADS has no available hourly AOD550 forecast cycle")


def forecast_request(base: datetime, boundary: Path) -> dict:
    if base.utcoffset() != timedelta(0) or base.hour not in (0, 12) or base.minute or base.second:
        raise ValueError("Forecast base must be 00 or 12 UTC")
    # Reuse the same guarded, study-area-only native grid request.
    request = request_for_days(base.date()+timedelta(days=1), base.date()+timedelta(days=1), boundary)
    request.update(date=[base.date().isoformat()], time=[base.strftime("%H:%M")],
                   leadtime_hour=[str(i) for i in range(121)])
    return request


def hourly_records(hours: dict, grid, model) -> list[dict]:
    records = []
    for valid, base, lead, field in sorted(hours.values(), key=lambda e: e[0]):
        cells, features, weights = [], [], []
        for row in grid.itertuples():
            aod = float(field[row.row, row.col])
            if not np.isfinite(aod) or aod < 0:
                continue
            cells.append([row.grid_id, round(aod, 5), None, 1])
            features.append(aod)
            weights.append(row.overlap_m2)
        mean = None
        if cells:
            prediction = model.predict(pd.DataFrame({"AOD 0.47": features}))
            for cell, value in zip(cells, prediction):
                cell[2] = round(float(value), 2)
            mean = round(float(np.average(prediction, weights=weights)), 2)
        records.append({"valid_time": valid.isoformat(), "forecast_base_time": base.isoformat(),
                        "lead_time_hours": [lead, lead], "status": "Available" if cells else "NoData",
                        "available_cells": len(cells), "mean_pm25": mean, "cells": cells})
    return records


def refresh(boundary: Path, model_path: Path, site_data: Path, raw: Path, token: str) -> Path:
    from ecmwf.datastores import Client
    client = Client(url=URL, key=token, maximum_tries=3, timeout=60, progress=False,
                    log_callback=lambda *a, **k: None)
    base = latest_cycle(client.get_collection(COLLECTION).constraints, datetime.now(timezone.utc))
    target = site_data/"cams_forecast.json"
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if previous.get("forecast_base_time") == base.isoformat() and len(previous.get("hours", [])) == 121:
            print("CAMS latest available forecast cycle is already published", flush=True)
            return target
    request = forecast_request(base, boundary)
    source = download_request(request, raw/f"cams_forecast_{base:%Y%m%d_%H}.zip", token)
    lat, lon, hours = read_hours([source])
    if len(hours) != 121 or any(e[1] != base for e in hours.values()) or {e[2] for e in hours.values()} != set(range(121)):
        raise ValueError("Downloaded forecast is not the complete requested 0–120 hour cycle")
    grid = native_grid(lat, lon, boundary)
    model = joblib.load(model_path)
    if list(getattr(model, "feature_names_in_", [])) != ["AOD 0.47"]:
        raise ValueError("Unexpected model features")
    records = hourly_records(hours, grid, model)
    if not all(r["available_cells"] == len(grid) for r in records):
        raise ValueError("Incomplete CAMS study-area forecast; keeping previous publication")
    payload = {"source": "CAMS AOD550 / Extra Trees", "time_zone": "Asia/Bangkok",
               "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "forecast_base_time": base.isoformat(), "resolution_degrees": .4,
               "grid_count": len(grid), "hours": records}
    site_data.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(target)
    print(f"CAMS forecast exported: base {base.isoformat()}, 121 hours, {len(grid)} clipped cells", flush=True)
    return target
