import json
import tempfile
import unittest
import os
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
from netCDF4 import Dataset
from pyproj import Transformer
from shapely.geometry import box

from viirs.fetch import COLLECTIONS, discover, identity
from viirs.process import daily_record, grid_id, quality_mask, reporting_grid, samples
from viirs.refresh import signature
from viirs.refresh import refresh


class Model:
    def predict(self, frame):
        assert list(frame.columns) == ['AOD 0.47']
        return frame.iloc[:, 0].to_numpy()*100


class ViirsTests(unittest.TestCase):
    def test_no_snpp_and_url_allowlist(self):
        self.assertEqual(set(COLLECTIONS), {'NOAA20', 'NOAA21'})
        url = 'https://sips-data.ssec.wisc.edu/nrt/1/AERDB_L2_VIIRS_NOAA20.A2026323.0642.021.nrt.nc'
        self.assertEqual(identity(url), 'NOAA20_2026323_0642')
        for bad in [url.replace('NOAA20', 'SNPP'), url.replace('.021.', '.020.'), url.replace('sips-data.ssec.wisc.edu', 'example.org')]:
            with self.assertRaises(ValueError):
                identity(bad)

    def test_world_search_is_rejected(self):
        with self.assertRaises(ValueError):
            discover([-180, -90, 180, 90], datetime(2026, 11, 19, tzinfo=timezone.utc), datetime(2026, 11, 20, tzinfo=timezone.utc))

    def test_scientific_qa_and_nodata(self):
        aod = np.array([0., .1, .2, .3, -.1, np.nan, 7.])
        qa = np.array([3, 2, 1, 0, 3, 3, 3])
        self.assertEqual(quality_mask(aod, qa, np.full(7, 8.), np.full(7, 100.)).tolist(), [True, True, False, False, False, False, False])
        with self.assertRaises(ValueError):
            quality_mask(aod, qa[:2], aod, aod)

    def test_clipped_grid_and_actual_pixel_centres(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boundary = root/'boundary.geojson'
            gpd.GeoDataFrame({'geometry': [box(100, 8, 100.1, 8.1)]}, crs=4326).to_file(boundary, driver='GeoJSON')
            grid, shape = reporting_grid(boundary)
            self.assertAlmostEqual(grid.overlap_m2.sum(), shape.area, delta=.001)
            nc = root/'test.nc'
            with Dataset(nc, 'w') as ds:
                ds.createDimension('x', 4)
                for name, values in {
                    'Aerosol_Optical_Thickness_550_Land_Best_Estimate': [.2, .5, .8, .9],
                    'Aerosol_Optical_Thickness_QA_Flag_Land': [3, 3, 1, 3],
                    'Latitude': [8.05, 20., 8.06, 8.06],
                    'Longitude': [100.05, 100., 100.06, 100.06]}.items():
                    variable = ds.createVariable(name, 'f4', ('x',), fill_value=-999)
                    variable[:] = values
                ds['Aerosol_Optical_Thickness_550_Land_Best_Estimate'][3] = -999
            values = samples(nc, shape)
            self.assertEqual(len(values), 1)
            self.assertAlmostEqual(values[0][1], .2)
            self.assertIn(values[0][0], set(grid.grid_id))

    def test_combine_platforms_before_original_model(self):
        grid = gpd.GeoDataFrame({'grid_id': ['a', 'b'], 'overlap_m2': [1., 3.], 'geometry': [box(0, 0, 1, 1), box(1, 0, 2, 1)]}, crs=32647)
        granules = [{'satellite': 'NOAA20', 'time_start': '2026-11-19T06:00:00Z'}, {'satellite': 'NOAA21', 'time_start': '2026-11-19T07:00:00Z'}]
        row = daily_record(date(2026, 11, 19), [('a', .1), ('a', .3), ('b', .4)], grid, Model(), granules)
        self.assertEqual(row['cells'], [['a', .2, 20., 2], ['b', .4, 40., 1]])
        self.assertEqual(row['mean_pm25'], 35.)
        self.assertEqual(row['period_start_utc'], '2026-11-18T17:00:00+00:00')
        self.assertEqual(row['satellites'], ['NOAA20', 'NOAA21'])

    def test_missing_cells_are_not_filled_or_zeroed(self):
        grid = gpd.GeoDataFrame({'grid_id': ['a', 'b'], 'overlap_m2': [1., 3.], 'geometry': [box(0, 0, 1, 1), box(1, 0, 2, 1)]}, crs=32647)
        row = daily_record(date(2026, 11, 19), [('a', .2)], grid, Model(), [])
        self.assertEqual(row['coverage_fraction'], .25)
        empty = daily_record(date(2026, 11, 19), [], grid, Model(), [])
        self.assertEqual(empty['status'], 'NoData')
        self.assertIsNone(empty['mean_pm25'])

    def test_standard_replaces_nrt_for_same_overpass(self):
        class Response:
            def raise_for_status(self): pass
            def json(self): return {'feed': {'entry': self.entries}}
        class Session:
            def get(self, url, params, timeout):
                response = Response()
                platform = 'NOAA20' if params['collection_concept_id'] in COLLECTIONS['NOAA20'].values() else 'NOAA21'
                standard = params['collection_concept_id'].endswith('-LAADS')
                filename = f'AERDB_L2_VIIRS_{platform}.A2026323.0642.021.'+('2026323000000' if standard else 'nrt')+'.nc'
                response.entries = [{'time_start': '2026-11-19T06:42:00Z', 'links': [{'rel': 'http://esipfed.org/ns/fedsearch/1.1/data#', 'href': 'https://sips-data.ssec.wisc.edu/nrt/1/'+filename}]}]
                return response
        rows, errors = discover([100, 8, 100.2, 8.3], datetime(2026, 11, 19, tzinfo=timezone.utc), datetime(2026, 11, 20, tzinfo=timezone.utc), Session())
        self.assertFalse(errors)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['stream'] == 'standard' for row in rows))

    def test_changed_processing_stream_invalidates_cache(self):
        old = [{'id': 'same-overpass', 'url': 'nrt', 'revision': '1'}]
        new = [{'id': 'same-overpass', 'url': 'standard', 'revision': '1'}]
        self.assertNotEqual(signature(old), signature(new))

    def test_download_failure_preserves_verified_data_and_original_update_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boundary = root/'boundary.geojson'
            gpd.GeoDataFrame({'geometry': [box(100, 8, 100.1, 8.1)]}, crs=4326).to_file(boundary, driver='GeoJSON')
            from viirs.process import THAI
            day = datetime.now(THAI).date().isoformat()
            item = {'id': 'observed', 'url': 'prior', 'satellite': 'NOAA20', 'revision': '1', 'time_start': day+'T06:00:00Z'}
            row = {'date': day, 'status': 'Available', 'available_cells': 1, 'mean_pm25': 20,
                   'cells': [['known', .2, 20, 1]], 'checked_at_utc': day+'T07:00:00Z', 'input_granules': [item]}
            (root/'viirs_history.json').write_text(json.dumps({'days': [row]}))
            changed = {**item, 'url': 'reprocessed', 'revision': '2'}
            with patch.dict(os.environ, {'NASA_EARTHDATA_TOKEN': 'test-only'}), patch('viirs.refresh.joblib.load', return_value=Model()), patch('viirs.refresh.discover', return_value=([changed], [])), patch('viirs.refresh.download', side_effect=RuntimeError('provider unavailable')):
                Model.feature_names_in_ = ['AOD 0.47']
                result = refresh(boundary, root/'model.pkl', root, days=1, max_days=1)
            self.assertEqual(result['days'][0], row)
            self.assertEqual(result['generated_at_utc'], row['checked_at_utc'])
            self.assertEqual(result['state'], 'partial')

    def test_incomplete_collection_inventory_cannot_remove_prior_platform(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boundary = root/'boundary.geojson'
            gpd.GeoDataFrame({'geometry': [box(100, 8, 100.1, 8.1)]}, crs=4326).to_file(boundary, driver='GeoJSON')
            from viirs.process import THAI
            day = datetime.now(THAI).date().isoformat()
            item = {'id': 'noaa21', 'url': 'prior', 'satellite': 'NOAA21', 'time_start': day+'T06:00:00Z'}
            row = {'date': day, 'status': 'Available', 'available_cells': 1, 'mean_pm25': 20,
                   'cells': [['known', .2, 20, 1]], 'checked_at_utc': day+'T07:00:00Z', 'input_granules': [item]}
            (root/'viirs_history.json').write_text(json.dumps({'days': [row]}))
            with patch.dict(os.environ, {'NASA_EARTHDATA_TOKEN': 'test-only'}), patch('viirs.refresh.joblib.load', return_value=Model()), patch('viirs.refresh.discover', return_value=([], ['NOAA21/nrt'])), patch('viirs.refresh.download', side_effect=AssertionError('No complete inventory to download')):
                Model.feature_names_in_ = ['AOD 0.47']
                result = refresh(boundary, root/'model.pkl', root, days=1, max_days=1)
            self.assertEqual(result['days'][0], row)
            self.assertEqual(result['state'], 'partial')


if __name__ == '__main__':
    unittest.main()
