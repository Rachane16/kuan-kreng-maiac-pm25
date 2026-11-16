"""Sample real MAIAC AOD to the supplied 1 km grid and run the saved model."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
from pyproj import Transformer

from .fetch import FILE_RE
from .archive import ARCHIVE_RE
from .qc import daily_aod, quality_mask
from .tiles import MODIS_CRS, TILE_WIDTH_M, X_MIN, Y_MAX

THAILAND = ZoneInfo("Asia/Bangkok")
ORBIT_RE = re.compile(r"(?P<year>\d{4})(?P<doy>\d{3})(?P<hour>\d{2})(?P<minute>\d{2})(?P<satellite>[TA])")


def orbit_times(metadata: object, count: int) -> list[datetime | None]:
    stamps = ORBIT_RE.findall(str(metadata))
    if len(stamps) != count:
        return [None] * count
    return [datetime(int(y), 1, 1, tzinfo=timezone.utc) + timedelta(days=int(d) - 1, hours=int(h), minutes=int(m))
            for y, d, h, m, _ in stamps]


def read_hdf(path: Path) -> tuple[np.ndarray, np.ndarray, dict, list[datetime | None]]:
    try:
        from pyhdf.SD import SD, SDC
    except ImportError as exc:
        raise RuntimeError("pyhdf is required to read HDF4 files; install requirements.txt") from exc
    source = SD(str(path), SDC.READ)
    try:
        aod_ds = source.select("Optical_Depth_047")
        datasets = source.datasets()
        qa_name = next((name for name in ("AOD_QA", "AOT_QA") if name in datasets), None)
        if qa_name is None:
            raise ValueError(f"No AOD quality layer found in {path.name}")
        qa_ds = source.select(qa_name)
        raw = np.asarray(aod_ds.get())
        qa = np.asarray(qa_ds.get())
        attrs = aod_ds.attributes()
        orbit_metadata = source.attributes().get("Orbit_time_stamp", "")
    finally:
        source.end()
    if raw.ndim == 2:
        raw, qa = raw[np.newaxis, ...], qa[np.newaxis, ...]
    if raw.ndim != 3 or qa.shape != raw.shape:
        raise ValueError(f"Unexpected AOD/QA dimensions in {path.name}: {raw.shape}, {qa.shape}")
    times = orbit_times(orbit_metadata, raw.shape[0])
    required = ("scale_factor", "add_offset", "_FillValue", "valid_range")
    missing = [key for key in required if key not in attrs]
    if missing:
        raise ValueError(f"Missing AOD attributes in {path.name}: {missing}")
    return raw, qa, attrs, times


def sample_file(path: Path, points_x: np.ndarray, points_y: np.ndarray) -> dict[int, dict]:
    match = FILE_RE.fullmatch(path.name) or ARCHIVE_RE.fullmatch(path.name)
    if not match:
        raise ValueError(f"Unexpected HDF filename: {path.name}")
    h, v = int(match.group("tile")[1:3]), int(match.group("tile")[4:6])
    left, top = X_MIN + h * TILE_WIDTH_M, Y_MAX - v * TILE_WIDTH_M
    raw, qa, attrs, times = read_hdf(path)
    _, nrows, ncols = raw.shape
    col = np.floor((points_x - left) * ncols / TILE_WIDTH_M).astype(int)
    row = np.floor((top - points_y) * nrows / TILE_WIDTH_M).astype(int)
    inside = (col >= 0) & (col < ncols) & (row >= 0) & (row < nrows)
    indices = np.flatnonzero(inside)
    if not len(indices):
        return {}
    sampled_raw = raw[:, row[indices], col[indices]]
    sampled_qa = qa[:, row[indices], col[indices]]
    params = {
        "scale_factor": float(attrs["scale_factor"]),
        "add_offset": float(attrs["add_offset"]),
        "fill_value": int(attrs["_FillValue"]),
        "valid_range": tuple(int(x) for x in attrs["valid_range"]),
    }
    aod, counts = daily_aod(sampled_raw, sampled_qa, **params)
    valid = quality_mask(sampled_raw, sampled_qa, fill_value=params["fill_value"], valid_range=params["valid_range"])
    scaled = (sampled_raw.astype(float) - params["add_offset"]) * params["scale_factor"]
    # A median of two orbits can be equally distant from both. Round only the
    # comparison so floating-point noise cannot change the chosen timestamp.
    delta = np.where(valid, np.round(np.abs(scaled - aod[np.newaxis, :]), 12), np.inf)
    selected_orbit = delta.argmin(axis=0)
    result = {}
    for j, i in enumerate(indices):
        acquisition = times[int(selected_orbit[j])] if counts[j] else None
        result[int(i)] = {
            "aod_value": float(aod[j]) if counts[j] else None,
            "valid_overpasses": int(counts[j]),
            "data_time_utc": acquisition.isoformat() if acquisition else None,
            "source_file": path.name,
        }
    return result


def process_files(hdf_paths: list[Path], grid_path: Path, boundary_path: Path, model_path: Path,
                  output_dir: Path) -> tuple[Path, Path]:
    if not hdf_paths:
        raise ValueError("No real HDF files supplied")
    grid = gpd.read_file(grid_path)
    boundary_frame = gpd.read_file(boundary_path)
    if grid.empty or grid.crs is None or "grid_id" not in grid:
        raise ValueError("Grid is empty, lacks CRS, or lacks grid_id")
    if boundary_frame.empty or boundary_frame.crs is None:
        raise ValueError("Boundary is empty or lacks CRS")
    grid = grid.to_crs("EPSG:32647").reset_index(drop=True)
    boundary = boundary_frame.to_crs("EPSG:32647").geometry.union_all()
    if grid.grid_id.duplicated().any():
        raise ValueError("Grid IDs must be unique")
    if grid.geometry.intersection(boundary).is_empty.any():
        raise ValueError("Every grid cell must overlap the boundary")
    points = grid.geometry.intersection(boundary).representative_point()
    transformer = Transformer.from_crs("EPSG:32647", MODIS_CRS, always_xy=True)
    x, y = transformer.transform(points.x.to_numpy(), points.y.to_numpy())
    samples: dict[int, dict] = {}
    for path in hdf_paths:
        for index, value in sample_file(path, x, y).items():
            if index in samples:
                raise ValueError(f"Multiple HDF files cover grid cell {grid.iloc[index].grid_id}")
            samples[index] = value

    matches = [FILE_RE.fullmatch(p.name) or ARCHIVE_RE.fullmatch(p.name) for p in hdf_paths]
    if any(match is None for match in matches):
        raise ValueError("Unexpected HDF filename")
    product_days = {datetime.strptime(match.group("year") + match.group("doy"), "%Y%j").date() for match in matches}
    if len(product_days) != 1:
        raise ValueError("Input HDF files must have one UTC product date")
    product_date = product_days.pop()
    model = joblib.load(model_path)
    if list(getattr(model, "feature_names_in_", [])) != ["AOD 0.47"]:
        raise ValueError("Model feature names do not match the original notebook")
    rows = []
    processed_at = datetime.now(timezone.utc).isoformat()
    for i, grid_row in grid.iterrows():
        sample = samples.get(i, {})
        utc_time = sample.get("data_time_utc")
        local_time = datetime.fromisoformat(utc_time).astimezone(THAILAND).isoformat() if utc_time else None
        rows.append({
            "date": product_date.isoformat(),
            "grid_id": grid_row.grid_id,
            "source": "NASA_MCD19A2N" if FILE_RE.fullmatch(hdf_paths[0].name) else "NASA_MCD19A2",
            "aod_value": sample.get("aod_value"),
            "aod_wavelength_nm": 470,
            "predicted_pm25": None,
            "pm25_unit": "ug/m3",
            "data_time_utc": utc_time,
            "data_time_thailand": local_time,
            "processing_time": processed_at,
            "data_status": "Available" if sample.get("aod_value") is not None else "NoData",
            "valid_overpasses": sample.get("valid_overpasses", 0),
            "model_name": "ExtraTreesRegressor",
            "model_version": model_path.name,
            "source_file": sample.get("source_file"),
        })
    frame = pd.DataFrame(rows)
    available = frame.aod_value.notna()
    if available.any():
        features = pd.DataFrame({"AOD 0.47": frame.loc[available, "aod_value"].astype(float)})
        frame.loc[available, "predicted_pm25"] = model.predict(features)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"maiac_pm25_{product_date}.csv"
    geojson_path = output_dir / f"maiac_pm25_{product_date}.geojson"
    frame.to_csv(csv_path, index=False)
    # Keep the reporting grid IDs, but publish only the part of each cell
    # inside the user's study boundary.
    clipped_geometry = grid.geometry.intersection(boundary)
    output = gpd.GeoDataFrame(frame, geometry=clipped_geometry, crs=grid.crs).to_crs("EPSG:4326")
    output.to_file(geojson_path, driver="GeoJSON")
    metadata = {
        "product_date_utc": product_date.isoformat(),
        "processing_time_utc": processed_at,
        "source": "NASA MCD19A2N AOD 470 nm" if FILE_RE.fullmatch(hdf_paths[0].name) else "NASA MCD19A2 AOD 470 nm",
        "status": "Available" if available.any() else "NoData",
        "available_cells": int(available.sum()),
        "total_cells": len(frame),
        "aggregation": "median of valid overpasses; timestamp is the overpass nearest the median",
        "spatial_method": "sample MAIAC pixel at a representative point inside each intersecting 1 km UTM grid cell; clip GeoJSON polygons to the study boundary",
        "qa": "land, clear cloud mask, normal adjacency, best AOD quality",
        "model": model_path.name,
        "hdf_files": [p.name for p in hdf_paths],
    }
    (output_dir / f"maiac_pm25_{product_date}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return csv_path, geojson_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict PM2.5 from downloaded NASA MCD19A2N HDF files")
    parser.add_argument("--hdf", type=Path, nargs="+", required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True, help="Trusted Extra Trees .pkl from the original notebook")
    parser.add_argument("--output", type=Path, default=Path("data/outputs"))
    args = parser.parse_args()
    csv_path, geojson_path = process_files(args.hdf, args.grid, args.boundary, args.model, args.output)
    print(f"Wrote {csv_path} and {geojson_path}")


if __name__ == "__main__":
    main()
