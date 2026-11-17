"""Refresh only new or recently provisional MAIAC dates and keep a rolling 92 days."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .backfill import backfill
from .export_site import export_site


def refresh(end: date, days: int, boundary: Path, grid: Path, model: Path,
            site_data: Path, raw: Path, output: Path, token: str) -> tuple[Path, Path]:
    if days < 1:
        raise ValueError("days must be positive")
    if not token:
        raise ValueError("NASA_EARTHDATA_TOKEN is required")
    start = end - timedelta(days=days - 1)
    history_file = site_data / "history.json"
    previous = json.loads(history_file.read_text(encoding="utf-8")) if history_file.exists() else {}
    old_days = {item["date"]: item for item in previous.get("days", [])}
    to_check = []
    current = start
    while current <= end:
        item = old_days.get(current.isoformat())
        if (item is None or item.get("status") in {"NotPublished", "NotChecked"}
                or current >= end - timedelta(days=2)):
            to_check.append(current)
        current += timedelta(days=1)
    for day in to_check:
        backfill(day, day, boundary, grid, model, raw, output, token, force=True)
    files = export_site(start, end, boundary, grid, output, site_data, require_complete=True)
    print(f"Refreshed {len(to_check)} NASA dates; window {start} to {end}")
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh a rolling MAIAC dashboard")
    parser.add_argument("--end", type=date.fromisoformat,
                        default=datetime.now(timezone.utc).date() - timedelta(days=1))
    parser.add_argument("--days", type=int, default=92)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--site-data", type=Path, default=Path("docs/data"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw/maiac"))
    parser.add_argument("--output", type=Path, default=Path("data/outputs"))
    args = parser.parse_args()
    refresh(args.end, args.days, args.boundary, args.grid, args.model,
            args.site_data, args.raw, args.output, os.getenv("NASA_EARTHDATA_TOKEN", ""))


if __name__ == "__main__":
    main()
