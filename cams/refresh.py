"""Refresh a rolling CAMS daily history without redownloading checked dates."""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .fetch import download
from .process import export


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", type=date.fromisoformat, default=datetime.now(timezone.utc).date()-timedelta(days=1))
    parser.add_argument("--days", type=int, default=92)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--site-data", type=Path, default=Path("docs/data"))
    parser.add_argument("--raw", type=Path, default=Path("data/raw/cams"))
    args = parser.parse_args()
    if args.days<1:
        raise ValueError("days must be positive")
    start = args.end-timedelta(days=args.days-1)
    path = args.site_data/"cams_history.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    old = {r["date"]: r for r in previous.get("days", [])}
    pending = [start+timedelta(days=n) for n in range(args.days)
               if old.get((start+timedelta(days=n)).isoformat(), {}).get("status") != "Available"]
    first = min(pending) if pending else args.end
    token = os.getenv("CAMS_ADS_TOKEN", "")
    source = download(first, args.end, args.boundary, args.raw, token)
    export([source], start, args.end, args.boundary, args.model, args.site_data)


if __name__ == "__main__":
    main()
