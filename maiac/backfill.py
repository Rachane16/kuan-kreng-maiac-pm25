"""Backfill a date range for the exact MODIS tile(s) touching a boundary."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .archive import discover_range, download as download_archive
from .fetch import discover, download as download_nrt
from .process import process_files
from .tiles import tiles_for_boundary


def _session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def backfill(start: date, end: date, boundary: Path, grid: Path, model: Path,
             raw_dir: Path, output_dir: Path, token: str) -> Path:
    if end < start:
        raise ValueError("End date is before start date")
    if not token:
        raise ValueError("NASA_EARTHDATA_TOKEN is required")
    tiles = tiles_for_boundary(boundary)
    if not tiles:
        raise ValueError("Study boundary does not intersect any MODIS tile")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "backfill_manifest.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    days: dict[str, dict] = existing.get("days", {})
    session = _session()
    archive_urls = discover_range(start, end, tiles, session)
    current = start
    while current <= end:
        key = current.isoformat()
        metadata_path = output_dir / f"maiac_pm25_{key}.json"
        csv_path = output_dir / f"maiac_pm25_{key}.csv"
        if metadata_path.exists() and csv_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            days[key] = {"status": metadata["status"], "available_cells": metadata["available_cells"]}
            print(f"{key}: cached, {metadata['available_cells']} cells", flush=True)
        else:
            archive = archive_urls.get(current, [])
            urls = archive or discover(current, tiles, session)
            if not urls:
                days[key] = {"status": "NotPublished", "available_cells": 0}
                print(f"{key}: no matching NASA file", flush=True)
            else:
                downloader = download_archive if archive else download_nrt
                paths = [downloader(url, raw_dir / key, token, session) for url in urls]
                process_files(paths, grid, boundary, model, output_dir)
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                days[key] = {"status": metadata["status"], "available_cells": metadata["available_cells"]}
                print(f"{key}: {metadata['available_cells']} cells", flush=True)
        manifest_path.write_text(json.dumps({"tiles": sorted(tiles), "days": days}, indent=2), encoding="utf-8")
        current += timedelta(days=1)
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill real MAIAC data for a study boundary")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/maiac"))
    parser.add_argument("--output", type=Path, default=Path("data/outputs"))
    args = parser.parse_args()
    path = backfill(args.start, args.end, args.boundary, args.grid, args.model,
                    args.raw, args.output, os.getenv("NASA_EARTHDATA_TOKEN", ""))
    print(f"Manifest: {path}")


if __name__ == "__main__":
    main()
