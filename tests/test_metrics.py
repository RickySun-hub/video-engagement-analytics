from pathlib import Path
import math
import sys
import unittest
import duckdb
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from metrics import shapley_product,wilson,mix_decomposition

class DecompositionTests(unittest.TestCase):
    def test_single_driver(self):
        values=shapley_product({'users':10,'frequency':4,'seconds':5},{'users':20,'frequency':4,'seconds':5})
        for key,expected in {'users':200.0,'frequency':0.0,'seconds':0.0}.items():
            self.assertAlmostEqual(values[key],expected)

    def test_reconciles_mixed_directions_and_zero(self):
        for a,b in [({'a':2,'b':5,'c':7},{'a':3,'b':4,'c':9}),({'a':0,'b':5},{'a':3,'b':4})]:
            self.assertAlmostEqual(sum(shapley_product(a,b).values()),math.prod(b.values())-math.prod(a.values()))

    def test_order_independent(self):
        a={'a':2,'b':3};b={'a':4,'b':5}
        self.assertEqual(shapley_product(a,b),shapley_product(dict(reversed(list(a.items()))),dict(reversed(list(b.items())))))

    def test_mix_matches_known_shift(self):
        rows=mix_decomposition({'short':(50,10),'long':(50,30)},{'short':(25,10),'long':(75,30)})
        self.assertAlmostEqual(sum(r['mix_seconds'] for r in rows),5)
        self.assertEqual(sum(r['within_seconds'] for r in rows),0)

    def test_missing_segment_not_invented(self):
        with self.assertRaises(ValueError):mix_decomposition({'a':(1,2)},{'b':(1,2)})

    def test_wilson_empty_and_boundaries(self):
        self.assertEqual(wilson(0,0),(None,None))
        self.assertAlmostEqual(wilson(0,10)[0],0)
        self.assertAlmostEqual(wilson(10,10)[1],1)
        with self.assertRaises(ValueError):wilson(11,10)

class EventContractTests(unittest.TestCase):
    def setUp(self):
        self.con=duckdb.connect()
        def event(user,date,video=1,play=20000,duration=10000,rand=0,time=1):
            return dict(user_id=user,video_id=video,date=date,time_ms=time,
                        duration_ms=duration,play_time_ms=play,is_rand=rand,tab=0,
                        long_view=int(play>=min(duration,18000)),source_file='fixture')
        rows=[event(1,20220408),event(1,20220408), # exact duplicate
              event(1,20220409,time=2),event(1,20220415,time=3),
              event(2,20220507),event(2,20220508,time=4), # D1 eligible, D7 censored
              event(3,20220508), # both horizons censored
              event(4,20220408,duration=0), # invalid duration
              event(5,20220408,rand=1), # random exposure excluded from main KPI
              event(6,20220408,video=2,play=17000,duration=30000),
              event(6,20220408,video=2,play=18000,duration=30000,time=5)]
        self.con.register('fixture',pd.DataFrame(rows))
        self.con.execute('CREATE TABLE raw AS SELECT * FROM fixture')
        self.con.execute((ROOT/'sql/01_clean.sql').read_text())
        self.con.execute((ROOT/'sql/02_marts.sql').read_text())

    def tearDown(self):self.con.close()

    def test_exact_duplicates_only(self):
        self.assertEqual(self.con.execute('SELECT count(*) FROM deduplicated').fetchone()[0],10)
        self.assertEqual(self.con.execute('SELECT count(*) FROM standard_events WHERE user_id=6').fetchone()[0],2)

    def test_replay_kept_and_capped_separately(self):
        self.assertEqual(self.con.execute('SELECT watch_seconds,capped_watch_seconds FROM standard_events WHERE user_id=1 ORDER BY time_ms LIMIT 1').fetchone(),(20,10))

    def test_invalid_duration_quarantined(self):
        self.assertEqual(self.con.execute('SELECT count(*) FROM classified WHERE NOT is_valid').fetchone()[0],1)

    def test_random_not_in_primary(self):
        self.assertEqual(self.con.execute('SELECT count(*) FROM standard_events WHERE user_id=5').fetchone()[0],0)

    def test_exact_d7_not_within_7(self):
        # User 6 is observed twice on day zero, but has no day-seven return.
        self.assertEqual(self.con.execute('SELECT returned FROM return_observations WHERE user_id=6 AND horizon=7').fetchone()[0],False)
        self.assertEqual(self.con.execute('SELECT returned FROM return_observations WHERE user_id=1 AND horizon=7').fetchone()[0],True)

    def test_right_censoring(self):
        self.assertEqual(self.con.execute('SELECT horizon,eligible,returned FROM return_observations WHERE user_id=2 ORDER BY horizon').fetchall(),[(1,True,True),(7,False,False)])
        self.assertEqual(self.con.execute('SELECT count(*) FROM return_observations WHERE user_id=3 AND eligible').fetchone()[0],0)

    def test_long_view_threshold(self):
        self.assertEqual(self.con.execute('SELECT derived_long_view FROM standard_events WHERE user_id=6 ORDER BY time_ms').fetchall(),[(0,),(1,)])

    def test_future_outcomes_not_in_features(self):
        self.assertEqual(self.con.execute('SELECT early_watch_seconds,next_watch_seconds FROM audience_observations WHERE user_id=1').fetchone(),(40,20))

if __name__=='__main__':unittest.main()
