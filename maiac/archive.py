"""Discover historical MCD19A2 tiles through NASA CMR and download LP DAAC files."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests

from .fetch import HDF4_MAGIC

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
ARCHIVE_HOST = "data.lpdaac.earthdatacloud.nasa.gov"
ARCHIVE_RE = re.compile(r"^MCD19A2\.A(?P<year>\d{4})(?P<doy>\d{3})\.(?P<tile>h\d{2}v\d{2})\.061\.\d{13}\.hdf$")


def discover_range(start: date, end: date, tiles: set[str],
                   session: requests.Session | None = None) -> dict[date, list[str]]:
    """Get only requested tile IDs in one CMR query; never request global granules."""
    if end < start or not tiles:
        raise ValueError("A date range and at least one tile are required")
    session = session or requests.Session()
    found: dict[date, list[str]] = {}
    for tile in sorted(tiles):
        params = {
            "short_name": "MCD19A2", "version": "061",
            "temporal": f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z",
            "producer_granule_id": f"*{tile}*",
            "options[producer_granule_id][pattern]": "true", "page_size": "2000",
        }
        response = session.get(CMR_URL, params=params, timeout=60)
        response.raise_for_status()
        for entry in response.json().get("feed", {}).get("entry", []):
            filename = str(entry.get("producer_granule_id", "")) + ".hdf"
            match = ARCHIVE_RE.fullmatch(filename)
            if not match or match.group("tile") != tile:
                continue
            day = date(int(match.group("year")), 1, 1) + timedelta(days=int(match.group("doy")) - 1)
            if not start <= day <= end:
                continue
            urls = [link.get("href", "") for link in entry.get("links", [])]
            valid_urls = [url for url in urls if _valid_url(url) and Path(urlparse(url).path).name == filename]
            if valid_urls:
                found.setdefault(day, []).append(valid_urls[0])
    return {day: sorted(urls) for day, urls in found.items()}


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.netloc == ARCHIVE_HOST
            and parsed.path.startswith("/lp-prod-protected/MCD19A2.061/")
            and ARCHIVE_RE.fullmatch(Path(parsed.path).name) is not None)


def download(url: str, target_dir: Path, token: str,
             session: requests.Session | None = None) -> Path:
    if not token:
        raise ValueError("NASA_EARTHDATA_TOKEN is required")
    if not _valid_url(url):
        raise ValueError("Unexpected LP DAAC download URL")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(urlparse(url).path).name
    if target.exists():
        with target.open("rb") as stream:
            if stream.read(4) == HDF4_MAGIC:
                return target
    session = session or requests.Session()
    temporary = target.with_suffix(".hdf.part")
    try:
        with session.get(url, headers={"Authorization": f"Bearer {token}"},
                         stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
        with temporary.open("rb") as stream:
            if stream.read(4) != HDF4_MAGIC:
                raise ValueError("NASA response is not an HDF4 file")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
