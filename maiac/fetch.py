"""Discover and download MCD19A2N files from NASA's NRT archive."""

from __future__ import annotations

import argparse
import os
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

BASE_URL = "https://nrt3.modaps.eosdis.nasa.gov/archive/allData/61/MCD19A2N/"
FILE_RE = re.compile(r"^MCD19A2N\.A(?P<year>\d{4})(?P<doy>\d{3})\.(?P<tile>h\d{2}v\d{2})\.061\.hdf$")
HDF4_MAGIC = b"\x0e\x03\x13\x01"


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def daily_url(day: date) -> str:
    return f"{BASE_URL}{day.year}/{day.timetuple().tm_yday:03d}/"


def parse_listing(html: str, day: date, tiles: set[str]) -> list[str]:
    parser = _Links()
    parser.feed(html)
    base = daily_url(day)
    found: set[str] = set()
    for href in parser.hrefs:
        name = Path(urlparse(href).path).name
        match = FILE_RE.fullmatch(name)
        if not match or match.group("tile") not in tiles:
            continue
        if match.group("year") != str(day.year) or int(match.group("doy")) != day.timetuple().tm_yday:
            continue
        url = urljoin(base, href)
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.netloc == urlparse(BASE_URL).netloc and parsed.path.startswith(urlparse(BASE_URL).path):
            found.add(url)
    return sorted(found)


def discover(day: date, tiles: set[str], session: requests.Session | None = None) -> list[str]:
    if not tiles:
        raise ValueError("At least one MODIS tile is required")
    session = session or requests.Session()
    response = session.get(daily_url(day), timeout=30)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return parse_listing(response.text, day, tiles)


def download(url: str, target_dir: Path, token: str, session: requests.Session | None = None) -> Path:
    if not token:
        raise ValueError("NASA_EARTHDATA_TOKEN is required to download HDF files")
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if parsed.scheme != "https" or parsed.netloc != urlparse(BASE_URL).netloc or not FILE_RE.fullmatch(name):
        raise ValueError("Unexpected MAIAC download URL")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    if target.exists():
        with target.open("rb") as existing:
            if existing.read(4) == HDF4_MAGIC:
                return target
    session = session or requests.Session()
    temp = target.with_suffix(".hdf.part")
    try:
        with session.get(url, headers={"Authorization": f"Bearer {token}"}, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            with temp.open("wb") as out:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out.write(chunk)
        with temp.open("rb") as inp:
            if inp.read(4) != HDF4_MAGIC:
                raise ValueError("NASA response is not an HDF4 file; check token and URL")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch NASA MCD19A2N tiles for a supplied study boundary")
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="UTC product date, YYYY-MM-DD")
    parser.add_argument("--boundary", type=Path, required=True, help="Existing KK-PSF boundary vector file")
    parser.add_argument("--output", type=Path, default=Path("data/raw/maiac"))
    parser.add_argument("--list-only", action="store_true", help="List matching files without downloading")
    args = parser.parse_args()
    from .tiles import tiles_for_boundary

    tiles = tiles_for_boundary(args.boundary)
    urls = discover(args.date, tiles)
    print(f"UTC date: {args.date}; MODIS tiles: {', '.join(sorted(tiles))}; files: {len(urls)}")
    for url in urls:
        if args.list_only:
            print(url)
        else:
            path = download(url, args.output / args.date.isoformat(), os.getenv("NASA_EARTHDATA_TOKEN", ""))
            print(path)
    if not urls:
        print("No MCD19A2N files found for this date and boundary; no output was fabricated.")


if __name__ == "__main__":
    main()
