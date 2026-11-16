"""One-command MAIAC download and prediction for a chosen UTC product date."""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from .fetch import discover, download
from .process import process_files
from .tiles import tiles_for_boundary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MAIAC AOD to PM2.5 for one UTC date")
    parser.add_argument("--date", type=date.fromisoformat, required=True, help="UTC product date, YYYY-MM-DD")
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True, help="Trusted original Extra Trees .pkl")
    parser.add_argument("--raw", type=Path, default=Path("data/raw/maiac"))
    parser.add_argument("--output", type=Path, default=Path("data/outputs"))
    args = parser.parse_args()

    tiles = tiles_for_boundary(args.boundary)
    urls = discover(args.date, tiles)
    if not urls:
        raise SystemExit(f"No MAIAC files found for {args.date} and tiles {sorted(tiles)}; no prediction created")
    token = os.getenv("NASA_EARTHDATA_TOKEN", "")
    if not token:
        raise SystemExit("Set NASA_EARTHDATA_TOKEN before downloading; no prediction created")
    paths = [download(url, args.raw / args.date.isoformat(), token) for url in urls]
    csv_path, geojson_path = process_files(paths, args.grid, args.boundary, args.model, args.output)
    print(f"Wrote {csv_path} and {geojson_path}")


if __name__ == "__main__":
    main()
