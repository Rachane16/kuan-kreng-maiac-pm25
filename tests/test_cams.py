"""CAMS spatial and Thai-day aggregation checks."""
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np

from cams.fetch import request_for_days
from cams.process import daily_record, native_grid
from cams.forecast import latest_cycle, forecast_request, hourly_records

BOUNDARY=Path(__file__).resolve().parents[1]/"data/boundaries/kkpsf_boundary.geojson"


class RecordingModel:
    def predict(self, frame):
        assert list(frame.columns)==["AOD 0.47"]
        return frame["AOD 0.47"].to_numpy()*2


class CAMSTests(unittest.TestCase):
    def setUp(self):
        self.grid=native_grid(np.array([8.4,8,7.6]),np.array([99.6,100,100.4]),BOUNDARY)
        self.start=datetime(2026,11,15,17,tzinfo=timezone.utc)
        self.base=datetime(2026,11,15,12,tzinfo=timezone.utc)
        self.hours={}
        for h in range(24):
            t=self.start+timedelta(hours=h)
            self.hours[t.isoformat()]=(t,self.base,h+5,np.full((3,3),(h+1)/100))

    def test_request_is_small_and_covers_exact_thai_day(self):
        r=request_for_days(date(2026,11,16),date(2026,11,16),BOUNDARY)
        self.assertEqual(r['area'],[8.4,99.6,7.6,100.4])
        self.assertEqual(r['date'],['2026-11-15/2026-11-15'])
        self.assertEqual(r['time'],['12:00'])
        self.assertEqual(r['leadtime_hour'],[str(i) for i in range(5,29)])

    def test_native_cells_cover_boundary_without_adding_resolution(self):
        self.assertEqual(len(self.grid),5)
        expected=gpd.read_file(BOUNDARY).to_crs(32647).geometry.union_all()
        actual=self.grid.to_crs(32647).geometry.union_all()
        self.assertLess(actual.symmetric_difference(expected).area,1)
        self.assertTrue((self.grid.overlap_m2>0).all())

    def test_daily_mean_uses_24_hours_before_original_model(self):
        r=daily_record(date(2026,11,16),self.hours,self.grid,RecordingModel())
        self.assertEqual(r['status'],'Available')
        self.assertEqual(r['available_hours'],24)
        self.assertEqual(r['forecast_base_time'],'2026-11-15T12:00:00+00:00')
        self.assertEqual(r['lead_time_hours'],[5,28])
        self.assertEqual(r['period_start_utc'],'2026-11-15T17:00:00+00:00')
        self.assertEqual(r['period_end_utc'],'2026-11-16T17:00:00+00:00')
        for c in r['cells']:
            self.assertEqual(c[1:],[.125,.25,24])

    def test_partial_and_missing_days_do_not_receive_daily_predictions(self):
        self.hours.pop(self.start.isoformat())
        r=daily_record(date(2026,11,16),self.hours,self.grid,RecordingModel())
        self.assertEqual(r['status'],'Incomplete')
        self.assertEqual(r['cells'],[])
        self.assertIsNone(r['mean_pm25'])
        self.assertEqual(daily_record(date(2026,11,16),{},self.grid,RecordingModel())['status'],'NotPublished')

    def test_invalid_aod_is_not_filled_and_forecast_cycles_are_checked(self):
        item=self.hours[self.start.isoformat()]
        item[3][:]=-1
        r=daily_record(date(2026,11,16),self.hours,self.grid,RecordingModel())
        self.assertEqual(r['status'],'NoData')
        self.assertEqual(r['cells'],[])
        self.hours[self.start.isoformat()]=(item[0],item[1]+timedelta(hours=12),item[2],item[3])
        with self.assertRaises(ValueError):
            daily_record(date(2026,11,16),self.hours,self.grid,RecordingModel())

    def test_forecast_cycle_uses_published_availability_and_union_of_steps(self):
        rows=[dict(variable=['total_aerosol_optical_depth_550nm'],type=['forecast'],
                   date=['2026-11-15/2026-11-17'],time=['00:00','12:00'],
                   leadtime_hour=[str(h) for h in range(121) if h%6==remainder])
              for remainder in range(6)]
        now=datetime(2026,11,17,10,tzinfo=timezone.utc)
        self.assertEqual(latest_cycle(rows,now),now.replace(hour=0))
        for r in rows:r['date']=['2026-11-15/2026-11-16']
        self.assertEqual(latest_cycle(rows,now),datetime(2026,11,16,12,tzinfo=timezone.utc))
        with self.assertRaises(ValueError):latest_cycle(rows[:1],now)

    def test_forecast_request_is_bounded_and_covers_120_hours(self):
        r=forecast_request(self.base,BOUNDARY)
        self.assertEqual(r['area'],[8.4,99.6,7.6,100.4])
        self.assertEqual(r['date'],['2026-11-15'])
        self.assertEqual(r['leadtime_hour'],[str(i) for i in range(121)])

    def test_hourly_prediction_preserves_valid_time_and_area_weighting(self):
        field=np.arange(9,dtype=float).reshape(3,3)/10
        records=hourly_records({self.start.isoformat():(self.start,self.base,5,field)},self.grid,RecordingModel())
        record=records[0]
        self.assertEqual(record['valid_time'],self.start.isoformat())
        self.assertEqual(record['forecast_base_time'],self.base.isoformat())
        self.assertEqual(record['lead_time_hours'],[5,5])
        self.assertEqual(record['available_cells'],5)
        weights={r.grid_id:r.overlap_m2 for r in self.grid.itertuples()}
        expected=np.average([c[2] for c in record['cells']],weights=[weights[c[0]] for c in record['cells']])
        self.assertEqual(record['mean_pm25'],round(expected,2))
        self.assertTrue(all(c[3]==1 for c in record['cells']))


if __name__=='__main__':unittest.main()
