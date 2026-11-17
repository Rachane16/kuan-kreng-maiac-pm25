"""Request only the native CAMS grid surrounding the supplied study boundary."""
from __future__ import annotations

import json
import math
import time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd

COLLECTION = "cams-global-atmospheric-composition-forecasts"
URL = "https://ads.atmosphere.copernicus.eu/api"


def request_for_days(start: date, end: date, boundary: Path) -> dict:
    if end < start:
        raise ValueError("End precedes start")
    frame = gpd.read_file(boundary)
    if frame.empty or frame.crs is None:
        raise ValueError("Invalid boundary")
    w, s, e, n = frame.to_crs(4326).total_bounds
    # Include only neighbouring native 0.4 degree grid centres needed at the edge.
    area = [round(math.ceil(n/.4)*.4, 4), round(math.floor(w/.4)*.4, 4),
            round(math.floor(s/.4)*.4, 4), round(math.ceil(e/.4)*.4, 4)]
    if (area[0]-area[2])*(area[3]-area[1]) > 4:
        raise ValueError("CAMS request area exceeds this project's 4 square degree limit")
    first, last = start-timedelta(days=1), end-timedelta(days=1)
    return {"variable": ["total_aerosol_optical_depth_550nm"],
            "date": [f"{first}/{last}"], "time": ["12:00"],
            "leadtime_hour": [str(i) for i in range(5, 29)],
            "type": ["forecast"], "data_format": "netcdf_zip", "area": area}


def download(start: date, end: date, boundary: Path, output: Path, token: str) -> Path:
    request = request_for_days(start, end, boundary)
    return download_request(request, output / f"cams_aod550_{start}_{end}.zip", token)


def download_request(request: dict, target: Path, token: str) -> Path:
    """Resume one bounded request, caching only by its exact parameters."""
    if not token:
        raise ValueError("CAMS_ADS_TOKEN is required")
    from ecmwf.datastores import Client
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt = target.with_suffix(".request.json")
    client = Client(url=URL, key=token, maximum_tries=3, retry_after=5,
                    timeout=60, progress=False, log_callback=lambda *a, **k: None)
    if receipt.exists():
        stored = json.loads(receipt.read_text(encoding="utf-8"))
        if stored["request"] != request:
            raise ValueError("Stored CAMS request parameters differ")
        if target.exists():
            return target
        remote = client.get_remote(stored["request_id"])
    else:
        remote = client.submit(COLLECTION, request)
        receipt.write_text(json.dumps({"request_id": remote.request_id, "request": request}), encoding="utf-8")
    print(f"CAMS request {request['date']} {request['time']}; area N/W/S/E {request['area']}", flush=True)
    previous = None
    deadline = time.monotonic()+7200
    while time.monotonic() < deadline:
        remote.update()
        if remote.status != previous:
            print(f"CAMS {remote.status}", flush=True)
            previous = remote.status
        if remote.status == "successful":
            temporary = target.with_suffix(".zip.part")
            remote.download(str(temporary))
            temporary.replace(target)
            return target
        if remote.status in {"failed", "rejected", "dismissed"}:
            raise RuntimeError(f"CAMS request {remote.request_id} failed; inspect ADS Your requests")
        time.sleep(10)
    raise TimeoutError("CAMS request is still pending; rerun to resume the same request")
