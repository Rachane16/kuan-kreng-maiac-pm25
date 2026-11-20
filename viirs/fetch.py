"""CMR discovery: bounded area/time, v2.1, NOAA-20/21 only."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

COLLECTIONS = {
    "NOAA20": {"standard": "C4218100848-LAADS", "nrt": "C4218441839-ASIPS"},
    "NOAA21": {"standard": "C4218210959-LAADS", "nrt": "C4218441854-ASIPS"},
}
FILE_RE = re.compile(r"^AERDB_L2_VIIRS_(NOAA20|NOAA21)\.A(\d{7})\.(\d{4})\.021\.(?:nrt|\d+)\.nc$")
HOSTS = {"sips-data.ssec.wisc.edu", "data.laadsdaac.earthdatacloud.nasa.gov", "ladsweb.modaps.eosdis.nasa.gov"}


def identity(url):
    parsed = urlparse(url)
    match = FILE_RE.fullmatch(Path(parsed.path).name)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or not match:
        raise ValueError("Unrecognized VIIRS NOAA v2.1 data URL")
    return "_".join(match.groups())


def discover(bounds, start, end, session=None):
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90) or east-west > 2 or north-south > 2:
        raise ValueError("VIIRS search must use a small study-area bounding box")
    if end <= start or (end-start).days > 94:
        raise ValueError("VIIRS search must cover at most 94 days")
    session = session or requests.Session()
    found, errors = {}, []
    for satellite, streams in COLLECTIONS.items():
        for stream, collection in streams.items():
            try:
                page = 1
                while True:
                    response = session.get("https://cmr.earthdata.nasa.gov/search/granules.json", params={
                        "collection_concept_id": collection, "bounding_box": ",".join(map(str, bounds)),
                        "temporal": start.isoformat()+","+end.isoformat(), "page_size": 500,
                        "page_num": page, "sort_key": "start_date"}, timeout=(15, 90))
                    response.raise_for_status()
                    entries = response.json()["feed"]["entry"]
                    for entry in entries:
                        links = [link["href"] for link in entry.get("links", [])
                                 if not link.get("inherited") and "/data#" in link.get("rel", "")]
                        for url in links:
                            try:
                                key = identity(url)
                            except ValueError:
                                continue
                            if not key.startswith(satellite+"_"):
                                continue
                            item = {"id": key, "url": url, "satellite": satellite, "stream": stream,
                                    "time_start": entry["time_start"], "time_end": entry.get("time_end"),
                                    "revision": entry.get("updated", "")}
                            # Standard supersedes NRT for the same platform/acquisition.
                            if key not in found or stream == "standard":
                                found[key] = item
                            break
                    if len(entries) < 500:
                        break
                    page += 1
                    if page > 10:
                        raise ValueError("Unexpected granule volume for study area")
            except (requests.RequestException, ValueError, KeyError):
                errors.append(satellite+"/"+stream)
    return sorted(found.values(), key=lambda row: (row["time_start"], row["id"])), errors


def download(item, token, target_dir, session=None):
    identity(item["url"])
    if not token:
        raise ValueError("NASA_EARTHDATA_TOKEN is required")
    session = session or requests.Session()
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir/Path(urlparse(item["url"]).path).name
    temporary = target.with_suffix(".nc.part")
    try:
        # Scoped header only; requests strips it on cross-host redirects.
        with session.get(item["url"], headers={"Authorization": "Bearer "+token},
                         stream=True, timeout=(20, 120)) as response:
            if response.status_code != 200:
                raise RuntimeError(f"VIIRS {item['satellite']} {item['stream']}: HTTP {response.status_code}")
            size = 0
            with temporary.open("wb") as output:
                for block in response.iter_content(1024*1024):
                    size += len(block)
                    if size > 80*1024*1024:
                        raise ValueError("VIIRS granule exceeds the study-download size limit")
                    output.write(block)
        with temporary.open("rb") as source:
            if source.read(8) != b"\x89HDF\r\n\x1a\n":
                raise RuntimeError("VIIRS endpoint returned a login page instead of NetCDF4; Earthdata access must be authorized")
        temporary.replace(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)
