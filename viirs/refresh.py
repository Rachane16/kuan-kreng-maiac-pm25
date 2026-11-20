"""Refresh rolling VIIRS NOAA snapshots; keep verified data when a provider fails."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import joblib

from .fetch import discover, download
from .process import THAI, reporting_grid, samples, daily_record, grid_geojson


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)+"\n", encoding="utf-8")
    temporary.replace(path)


def signature(items):
    return sorted((item["id"], item["url"], item.get("revision", "")) for item in items)


def refresh(boundary_path, model_path, site_data, days=92, max_days=12):
    token = os.getenv("NASA_EARTHDATA_TOKEN", "")
    if not token:
        raise ValueError("NASA_EARTHDATA_TOKEN is required")
    if not 1 <= days <= 92 or not 1 <= max_days <= 92:
        raise ValueError("VIIRS rolling windows must be 1–92 days")
    today = datetime.now(THAI).date()
    first = today-timedelta(days=days-1)
    grid, boundary = reporting_grid(boundary_path)
    import geopandas as gpd
    bounds = gpd.read_file(boundary_path).to_crs(4326).total_bounds
    start = datetime.combine(first, time.min, THAI).astimezone(timezone.utc)
    end = datetime.combine(today+timedelta(days=1), time.min, THAI).astimezone(timezone.utc)
    items, errors = discover(bounds, start, end)
    by_day = {}
    for item in items:
        day = datetime.fromisoformat(item["time_start"].replace("Z", "+00:00")).astimezone(THAI).date().isoformat()
        if first.isoformat() <= day <= today.isoformat():
            by_day.setdefault(day, []).append(item)
    history_path = site_data/"viirs_history.json"
    previous = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {}
    old = {row["date"]: row for row in previous.get("days", [])}
    model = joblib.load(model_path)
    if list(getattr(model, "feature_names_in_", [])) != ["AOD 0.47"]:
        raise ValueError("Model differs from the trusted original Extra Trees input")
    changed, failed, succeeded = 0, [], 0
    result = {}
    for offset in reversed(range(days)):
        day = first+timedelta(days=offset)
        key = day.isoformat()
        granules = by_day.get(key, [])
        prior = old.get(key)
        blank = {"date": key, "status": "NotChecked", "available_cells": 0, "cells": [], "mean_pm25": None,
                 "input_granules": [], "coverage_fraction": 0}
        if prior and signature(prior.get("input_granules", [])) == signature(granules) and prior["status"] in ("Available", "NoData"):
            result[key] = prior
            continue
        if errors:
            # Incomplete CMR inventories must not erase previously discovered inputs.
            known = {item["id"] for item in granules}
            if prior and any(item["id"] not in known for item in prior.get("input_granules", [])):
                result[key] = prior
                continue
        if not granules:
            result[key] = prior or {**blank, "status": "NotPublished" if not errors else "NotChecked"}
            continue
        if changed >= max_days:
            result[key] = prior or blank
            continue
        changed += 1
        try:
            readings = []
            with tempfile.TemporaryDirectory(prefix="kk-viirs-") as temporary:
                for item in granules:
                    path = download(item, token, temporary)
                    readings.extend(samples(path, boundary))
                    path.unlink()
            record = daily_record(day, readings, grid, model, granules)
            record["checked_at_utc"] = datetime.now(timezone.utc).isoformat()
            result[key] = record
            succeeded += 1
            print(f"VIIRS {key}: {len(granules)} granules, {record['valid_pixels']} QA pixels, {record['available_cells']} study cells", flush=True)
        except Exception as error:
            result[key] = prior or blank
            failed.append(key)
            # Never log response bodies, headers, or tokens.
            print(f"VIIRS {key}: {type(error).__name__}: {str(error)[:200]}", flush=True)
            if len(failed) >= 2 and not succeeded:
                # Authentication/provider outages must not consume the entire backlog.
                changed = max_days
    checked_times = [row["checked_at_utc"] for row in result.values() if row.get("checked_at_utc")]
    updated = max(checked_times) if checked_times else previous.get("generated_at_utc")
    now = datetime.now(timezone.utc).isoformat()
    write(site_data/"viirs_grid.geojson", grid_geojson(grid))
    history = {"source": "VIIRS NOAA AOD550 / Extra Trees", "satellites": ["NOAA20", "NOAA21"],
               "version": "2.1", "time_zone": "Asia/Bangkok", "generated_at_utc": updated or now,
               "last_attempt_utc": now, "start_date": first.isoformat(), "end_date": today.isoformat(),
               "grid_count": len(grid), "reporting_grid_m": 6000, "native_resolution_km_at_nadir": 6,
               "aod_wavelength_nm": 550, "qa_flags": [2, 3],
               "aggregation": "Mean QA=2/3 land AOD550 samples of NOAA-20/21 in each 6 km UTM reporting cell and Thai day, then the original Extra Trees model",
               "model_input_column": "AOD 0.47", "model_wavelength_override_nm": 550,
               "model_use": "AOD550 into original Extra Trees as explicitly approved by project owner; no wavelength conversion or retraining",
               "state": "partial" if errors or failed else "ok", "collection_errors": errors,
               "failed_days": failed, "pending_days": sum(row["status"] == "NotChecked" for row in result.values()),
               "days": [result[key] for key in sorted(result)]}
    write(history_path, history)
    print(f"VIIRS NOAA: {succeeded} refreshed days; {history['pending_days']} pending; {len(failed)} failed", flush=True)
    if not checked_times and (errors or failed):
        raise RuntimeError("No VIIRS granule has been verified; published sources are retained")
    return history


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--site-data", type=Path, default=Path("docs/data"))
    parser.add_argument("--days", type=int, default=92)
    parser.add_argument("--max-days", type=int, default=12)
    args = parser.parse_args()
    refresh(args.boundary, args.model, args.site_data, args.days, args.max_days)


if __name__ == "__main__":
    main()
