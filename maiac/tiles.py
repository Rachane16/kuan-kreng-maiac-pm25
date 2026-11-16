"""Select MODIS sinusoidal tiles intersecting a user-supplied boundary."""

from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import box

RADIUS_M = 6_371_007.181
TILE_WIDTH_M = 2 * math.pi * RADIUS_M / 36
X_MIN = -math.pi * RADIUS_M
Y_MAX = math.pi * RADIUS_M / 2
MODIS_CRS = CRS.from_proj4(f"+proj=sinu +R={RADIUS_M} +nadgrids=@null +wktext")


def tiles_for_boundary(path: Path) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Boundary file not found: {path}")
    frame = gpd.read_file(path)
    if frame.empty or frame.crs is None:
        raise ValueError("Boundary is empty or lacks a CRS")
    shape = frame.to_crs(MODIS_CRS).geometry.union_all()
    if shape.is_empty:
        raise ValueError("Boundary has no valid geometry")
    west, south, east, north = shape.bounds
    h0 = max(0, math.floor((west - X_MIN) / TILE_WIDTH_M))
    h1 = min(35, math.floor((east - X_MIN) / TILE_WIDTH_M))
    v0 = max(0, math.floor((Y_MAX - north) / TILE_WIDTH_M))
    v1 = min(17, math.floor((Y_MAX - south) / TILE_WIDTH_M))
    result = set()
    for h in range(h0, h1 + 1):
        for v in range(v0, v1 + 1):
            left = X_MIN + h * TILE_WIDTH_M
            top = Y_MAX - v * TILE_WIDTH_M
            if shape.intersects(box(left, top - TILE_WIDTH_M, left + TILE_WIDTH_M, top)):
                result.add(f"h{h:02d}v{v:02d}")
    return result
