"""Reconcile the checked-in aggregates without downloading raw data."""
from pathlib import Path
import json
import math
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
def main():
    r=json.loads((ROOT/'reports/results.json').read_text());s=r['summary']
    daily=pd.read_csv(ROOT/'reports/daily.csv');segments=pd.read_csv(ROOT/'reports/duration_segments.csv')
    cohorts=pd.read_csv(ROOT/'reports/cohort_return.csv');pooled=pd.read_csv(ROOT/'reports/pooled_return.csv')
    assert all(r['checks'].values())
    assert daily.exposures.sum()==segments.exposures.sum()==s['exposures']
    assert math.isclose(daily.watch_hours.sum(),s['watch_hours'],abs_tol=1e-6)
    assert math.isclose(sum(r['shapley_hours'].values()),r['weekly_watch_change_hours'],abs_tol=1e-6)
    for row in pooled.itertuples():
        c=cohorts[cohorts.horizon==row.horizon]
        assert c.eligible_users.sum()==row.eligible_users
        assert c.returned_users.sum()==row.returned_users
        assert math.isclose(row.return_rate,row.returned_users/row.eligible_users)
    for file in (ROOT/'reports').glob('*.csv'):
        columns=pd.read_csv(file,nrows=0).columns
        assert 'user_id' not in columns and 'video_id' not in columns,f'Row-level identifiers in {file}'
    print('PASS: published aggregate totals, return denominators, decomposition and identifier exclusion')

if __name__=='__main__':main()
