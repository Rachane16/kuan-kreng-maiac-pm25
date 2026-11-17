"""Publish compact, boundary-clipped static data for a 3-month dashboard."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping


def export_site(start: date, end: date, boundary_path: Path, grid_path: Path,
                output_dir: Path, site_data_dir: Path, require_complete: bool = False) -> tuple[Path, Path]:
    if end < start:
        raise ValueError("End date is before start date")
    grid = gpd.read_file(grid_path).to_crs("EPSG:32647")
    boundary = gpd.read_file(boundary_path).to_crs("EPSG:32647").geometry.union_all()
    if grid.empty or grid.crs is None or "grid_id" not in grid:
        raise ValueError("Invalid grid")
    clipped = gpd.GeoDataFrame(grid[["grid_id", "coverage_fraction"]].copy(),
                               geometry=grid.geometry.intersection(boundary), crs=grid.crs).to_crs("EPSG:4326")
    points = grid.geometry.intersection(boundary).representative_point()
    features = [{"type": "Feature", "properties": {
        "grid_id": row.grid_id, "coverage_fraction": round(float(row.coverage_fraction), 4),
        "sample_x": round(float(points.iloc[i].x), 3),
        "sample_y": round(float(points.iloc[i].y), 3)},
        "geometry": mapping(row.geometry)} for i, row in enumerate(clipped.itertuples())]
    site_data_dir.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame({"name": ["Khuan Kreng Peat Swamp Forest"]},
                     geometry=[boundary], crs="EPSG:32647").to_crs("EPSG:4326").to_file(
                         site_data_dir / "boundary.geojson", driver="GeoJSON")
    grid_file = site_data_dir / "grid.geojson"
    grid_file.write_text(json.dumps({"type": "FeatureCollection", "features": features},
                                    ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    manifest_path = output_dir / "backfill_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"days": {}}
    history_file = site_data_dir / "history.json"
    previous = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else {}
    if previous and previous.get("grid_count") != len(features):
        raise ValueError("Existing site history uses a different grid")
    previous_days = {item["date"]: item for item in previous.get("days", [])}
    days = []
    current = start
    while current <= end:
        key = current.isoformat()
        metadata_path = output_dir / f"maiac_pm25_{key}.json"
        csv_path = output_dir / f"maiac_pm25_{key}.csv"
        record = {"date": key, "status": "NotChecked", "available_cells": 0,
                  "mean_pm25": None, "cells": []}
        checked = manifest.get("days", {}).get(key)
        if checked and checked["status"] == "NotPublished":
            record["status"] = "NotPublished"
        elif metadata_path.exists() and csv_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            frame = pd.read_csv(csv_path)
            valid = frame.loc[frame.aod_value.notna() & frame.predicted_pm25.notna()]
            record["status"] = metadata["status"]
            record["available_cells"] = int(len(valid))
            record["mean_pm25"] = round(float(valid.predicted_pm25.mean()), 2) if len(valid) else None
            record["cells"] = [[row.grid_id, round(float(row.aod_value), 4),
                                round(float(row.predicted_pm25), 2), row.data_time_utc,
                                int(row.valid_overpasses)] for row in valid.itertuples()]
        elif key in previous_days:
            record = previous_days[key]
        elif checked:
            record["status"] = checked["status"]
        days.append(record)
        current += timedelta(days=1)
    if require_complete and any(item["status"] == "NotChecked" for item in days):
        raise ValueError("Backfill is incomplete; refusing to publish unchecked dates")
    history_file.write_text(json.dumps({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "source": "NASA MCD19A2/MCD19A2N AOD 470 nm",
        "grid_count": len(features), "days": days,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return grid_file, history_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Export clipped grid and MAIAC history for a static site")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/outputs"))
    parser.add_argument("--site-data", type=Path, default=Path("site/data"))
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    files = export_site(args.start, args.end, args.boundary, args.grid,
                        args.output, args.site_data, args.require_complete)
    print("Wrote " + " and ".join(str(path) for path in files))


if __name__ == "__main__":
    main()
