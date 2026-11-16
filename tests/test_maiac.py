"""Small tests for NASA listing, QA filtering and boundary alignment."""

from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd

from maiac.fetch import daily_url, parse_listing
from maiac.archive import discover_range
from maiac.grid import create_grid
from maiac.process import process_files, read_hdf, sample_file
from maiac.qc import daily_aod, quality_mask
from maiac.tiles import TILE_WIDTH_M, X_MIN, Y_MAX, tiles_for_boundary


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / "data" / "boundaries" / "kkpsf_boundary.geojson"


class ListingTests(unittest.TestCase):
    def test_listing_selects_date_and_tile_only(self) -> None:
        day = date(2026, 11, 15)
        html = """<a href="MCD19A2N.A2026319.h27v08.061.hdf">target</a>
        <a href="MCD19A2N.A2026319.h26v08.061.hdf">other tile</a>
        <a href="MCD19A2N.A2026318.h27v08.061.hdf">other day</a>
        <a href="https://evil.example/MCD19A2N.A2026319.h27v08.061.hdf">external</a>"""
        self.assertEqual(
            parse_listing(html, day, {"h27v08"}),
            [daily_url(day) + "MCD19A2N.A2026319.h27v08.061.hdf"],
        )

    def test_archive_search_keeps_only_requested_tile_and_date(self) -> None:
        basename = "MCD19A2.A2026228.h27v08.061.2026230205109"
        url = ("https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/"
               f"MCD19A2.061/{basename}/{basename}.hdf")
        response = SimpleNamespace(json=lambda: {"feed": {"entry": [
            {"producer_granule_id": basename, "links": [{"href": url}]},
            {"producer_granule_id": basename.replace("h27v08", "h26v08"),
             "links": [{"href": url.replace("h27v08", "h26v08")}]},
            {"producer_granule_id": basename, "links": [{"href": "https://evil.example/file.hdf"}]},
        ]}}, raise_for_status=lambda: None)
        session = SimpleNamespace(get=lambda *args, **kwargs: response)
        self.assertEqual(discover_range(date(2026, 8, 16), date(2026, 8, 16),
                                        {"h27v08"}, session), {date(2026, 8, 16): [url]})


class QualityTests(unittest.TestCase):
    def test_mask_rejects_fill_cloud_and_low_quality(self) -> None:
        raw = np.array([[200, -28672, 300, 400, -10]])
        qa = np.array([[1, 1, 3, 0x101, 1]])
        np.testing.assert_array_equal(
            quality_mask(raw, qa, fill_value=-28672, valid_range=(-100, 4000)),
            [[True, False, False, False, False]],
        )

    def test_median_keeps_missing_cells(self) -> None:
        raw = np.array([[[100, -28672]], [[300, -28672]]])
        qa = np.ones_like(raw)
        aod, count = daily_aod(raw, qa, scale_factor=0.001, add_offset=0,
                               fill_value=-28672, valid_range=(-100, 4000))
        np.testing.assert_allclose(aod[0, 0], 0.2)
        self.assertTrue(np.isnan(aod[0, 1]))
        np.testing.assert_array_equal(count, [[2, 0]])


class HdfTests(unittest.TestCase):
    def test_hdf4_reader_uses_metadata_and_normalizes_one_orbit(self) -> None:
        try:
            from pyhdf.SD import SD, SDC
        except ImportError:
            self.skipTest("pyhdf is not installed")
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "one_orbit.hdf"
            source = SD(str(path), SDC.WRITE | SDC.CREATE)
            aod = source.create("Optical_Depth_047", SDC.INT16, (2, 2))
            aod.set(np.array([[200, -28672], [300, 400]], dtype=np.int16))
            aod.scale_factor = 0.001
            aod.add_offset = 0.0
            aod.attr("_FillValue").set(SDC.INT16, -28672)
            aod.valid_range = (-100, 4000)
            qa = source.create("AOD_QA", SDC.UINT16, (2, 2))
            qa.set(np.ones((2, 2), dtype=np.uint16))
            source.Orbit_time_stamp = "20263190300T"
            aod.endaccess()
            qa.endaccess()
            source.end()
            raw, flags, attrs, times = read_hdf(path)
        self.assertEqual(raw.shape, (1, 2, 2))
        self.assertEqual(flags.shape, raw.shape)
        self.assertEqual(int(attrs["_FillValue"]), -28672)
        self.assertEqual(times[0], datetime(2026, 11, 15, 3, tzinfo=timezone.utc))


class SpatialTests(unittest.TestCase):
    def test_supplied_boundary_grid_and_tile(self) -> None:
        grid = create_grid(BOUNDARY)
        self.assertEqual(len(grid), 1052)
        self.assertAlmostEqual(grid.overlap_m2.sum() / 1e6, 931.05, places=2)
        self.assertEqual(tiles_for_boundary(BOUNDARY), {"h27v08"})

    def test_sample_file_keeps_missing_pixel_and_orbit_time(self) -> None:
        name = Path("MCD19A2N.A2026319.h27v08.061.hdf")
        left = X_MIN + 27 * TILE_WIDTH_M
        top = Y_MAX - 8 * TILE_WIDTH_M
        x = np.array([left + TILE_WIDTH_M * 0.25, left + TILE_WIDTH_M * 0.75])
        y = np.array([top - TILE_WIDTH_M * 0.25, top - TILE_WIDTH_M * 0.75])
        raw = np.array([[[100, -28672], [200, -28672]],
                        [[300, -28672], [400, -28672]]])
        qa = np.ones_like(raw)
        attrs = {"scale_factor": 0.001, "add_offset": 0, "_FillValue": -28672,
                 "valid_range": (-100, 4000)}
        times = [datetime(2026, 11, 15, 3, tzinfo=timezone.utc),
                 datetime(2026, 11, 15, 6, tzinfo=timezone.utc)]
        with patch("maiac.process.read_hdf", return_value=(raw, qa, attrs, times)):
            result = sample_file(name, x, y)
        self.assertAlmostEqual(result[0]["aod_value"], 0.2)
        self.assertEqual(result[0]["valid_overpasses"], 2)
        self.assertEqual(result[0]["data_time_utc"], times[0].isoformat())
        self.assertIsNone(result[1]["aod_value"])
        self.assertIsNone(result[1]["data_time_utc"])

    def test_geojson_is_clipped_to_boundary_and_keeps_nodata(self) -> None:
        grid_path = ROOT / "data" / "boundaries" / "kkpsf_grid_1km.gpkg"
        fake_hdf = Path("MCD19A2N.A2026319.h27v08.061.hdf")
        with TemporaryDirectory() as temporary:
            with patch("maiac.process.sample_file", return_value={}), \
                 patch("maiac.process.joblib.load", return_value=SimpleNamespace(feature_names_in_=["AOD 0.47"])):
                csv_path, geojson_path = process_files([fake_hdf], grid_path, BOUNDARY,
                                                       Path("trusted_model.pkl"), Path(temporary))
            table = pd.read_csv(csv_path)
            self.assertEqual(len(table), 1052)
            self.assertTrue(table.predicted_pm25.isna().all())
            self.assertTrue((table.data_status == "NoData").all())
            output = gpd.read_file(geojson_path).to_crs("EPSG:32647")
            boundary = gpd.read_file(BOUNDARY).to_crs("EPSG:32647").geometry.union_all()
            self.assertLess(output.geometry.union_all().symmetric_difference(boundary).area, 1)


if __name__ == "__main__":
    unittest.main()
