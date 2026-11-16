"""Build aligned 1 km UTM cells from the supplied KK-PSF boundary."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

TARGET_CRS = "EPSG:32647"
CELL_M = 1000


def create_grid(boundary_path: Path) -> gpd.GeoDataFrame:
    boundary = gpd.read_file(boundary_path)
    if boundary.empty or boundary.crs is None:
        raise ValueError("Boundary is empty or lacks a CRS")
    shape = boundary.to_crs(TARGET_CRS).geometry.union_all()
    if shape.is_empty or not shape.is_valid:
        raise ValueError("Boundary geometry is empty or invalid")
    west, south, east, north = shape.bounds
    x0 = math.floor(west / CELL_M) * CELL_M
    y0 = math.floor(south / CELL_M) * CELL_M
    x1 = math.ceil(east / CELL_M) * CELL_M
    y1 = math.ceil(north / CELL_M) * CELL_M
    rows = []
    for easting in range(x0, x1, CELL_M):
        for northing in range(y0, y1, CELL_M):
            cell = box(easting, northing, easting + CELL_M, northing + CELL_M)
            overlap = shape.intersection(cell).area
            if overlap > 0:
                rows.append({
                    "grid_id": f"E{easting:06d}_N{northing:07d}",
                    "easting": easting,
                    "northing": northing,
                    "overlap_m2": round(overlap, 2),
                    "coverage_fraction": overlap / (CELL_M * CELL_M),
                    "geometry": cell,
                })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=TARGET_CRS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create 1 km grid cells intersecting a supplied boundary")
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/boundaries/kkpsf_grid_1km.gpkg"))
    args = parser.parse_args()
    grid = create_grid(args.boundary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    grid.to_file(args.output, driver="GPKG", layer="grid_1km")
    print(f"Wrote {len(grid)} cells to {args.output}; covered area {grid.overlap_m2.sum() / 1e6:.2f} km2")


if __name__ == "__main__":
    main()
