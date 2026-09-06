"""Reproduce SQL marts, quality checks and the published aggregate evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
import duckdb
import pandas as pd
from fetch_data import FILES, digest
from metrics import shapley_product, wilson, mix_decomposition

ROOT = Path(__file__).resolve().parents[1]
EXPORTS=['daily','duration_segments','scenario_segments','weekly_comparison',
         'duration_period','cohort_return','audience_segments']

def run(raw_dir, output_dir):
    output_dir.mkdir(parents=True,exist_ok=True)
    processed=ROOT/'data/processed';processed.mkdir(parents=True,exist_ok=True)
    provenance=json.loads((raw_dir/'provenance.json').read_text())
    for name in FILES:
        if digest(raw_dir/name) != provenance['files'][name]['sha256']:
            raise ValueError(f'Input checksum changed: {name}')
    con=duckdb.connect(str(processed/'engagement.duckdb'))
    con.execute("SET memory_limit='2GB'; SET threads=4; SET preserve_insertion_order=false")
    con.execute("SET temp_directory=?",[str(processed/'spill')])
    print('Loading all three event files',flush=True)
    paths=[str(raw_dir/name) for name in FILES]
    con.execute('CREATE OR REPLACE TABLE raw AS SELECT * EXCLUDE(filename),filename AS source_file FROM read_csv(?, union_by_name=true,filename=true)',[paths])
    schema=con.execute('DESCRIBE raw').fetchdf()
    required={'user_id','video_id','date','time_ms','duration_ms','play_time_ms','is_rand','tab','long_view'}
    if not required <= set(schema.column_name): raise ValueError('Required columns missing')
    nulls={name:con.execute(f'SELECT count(*)-count("{name}") FROM raw').fetchone()[0]
           for name in schema.column_name if name!='source_file'}
    source_counts=con.execute('SELECT source_file,count(*) AS rows FROM raw GROUP BY source_file').fetchdf()
    source_counts.source_file=source_counts.source_file.map(lambda x:Path(x).name)
    print('Auditing exact duplicates and event domains',flush=True)
    con.execute((ROOT/'sql/01_clean.sql').read_text())
    counts={table:con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
            for table in ['raw','deduplicated','classified','events','standard_events','user_day']}
    quality={'counts':counts,'null_counts':nulls,'schema':schema.to_dict('records'),
             'source_counts':source_counts.to_dict('records'),
             'exact_duplicate_rows_removed':counts['raw']-counts['deduplicated'],
             'invalid_rows_excluded':counts['classified']-counts['events']}
    quality.update(con.execute('''SELECT count(DISTINCT user_id) AS users,
      count(DISTINCT video_id) AS videos, min(event_date)::VARCHAR AS first_date,
      max(event_date)::VARCHAR AS last_date,
      count(*) FILTER (WHERE play_time_ms>duration_ms) AS extended_play_rows,
      count(*) FILTER (WHERE derived_long_view != long_view) AS long_view_definition_mismatches,
      count(*) FILTER (WHERE event_date != (epoch_ms(time_ms)+INTERVAL '8 hours')::DATE) AS utc_plus_8_date_mismatches,
      quantile_cont(watch_seconds,.99) AS p99_watch_seconds,
      max(watch_seconds) AS max_watch_seconds FROM events''').fetchdf().to_dict('records')[0])
    quality['candidate_key_duplicate_excess']=con.execute('''SELECT sum(n-1) FROM
      (SELECT count(*) n FROM deduplicated GROUP BY user_id,video_id,time_ms,tab,is_rand HAVING count(*)>1)''').fetchone()[0] or 0
    quality['policy_file_mismatches']=con.execute("""SELECT count(*) FROM raw WHERE
      (contains(source_file,'log_random_') AND is_rand!=1) OR
      (contains(source_file,'log_standard_') AND is_rand!=0)""").fetchone()[0]
    quality['zero_duration_rows']=con.execute('SELECT count(*) FROM classified WHERE duration_ms=0').fetchone()[0]
    quality['zero_duration_standard_watch_hours']=con.execute('SELECT coalesce(sum(play_time_ms)/3600000.0,0) FROM classified WHERE duration_ms=0 AND is_rand=0').fetchone()[0]
    quality['standard_recorded_long_view_rate']=con.execute('SELECT avg(long_view) FROM standard_events').fetchone()[0]
    con.execute("""SELECT date_diff('day', event_date, (epoch_ms(time_ms)+INTERVAL '8 hours')::DATE) AS date_offset_days,
      count(*) AS exposures FROM events GROUP BY 1 ORDER BY 1""").fetchdf().to_csv(output_dir/'date_alignment_audit.csv',index=False)
    con.execute('''SELECT tab, count(*) AS exposures,
      count(*) FILTER(WHERE derived_long_view != long_view) AS mismatches,
      avg(long_view) AS recorded_rate,avg(derived_long_view) AS derived_rate
      FROM events GROUP BY tab ORDER BY tab''').fetchdf().to_csv(output_dir/'long_view_audit.csv',index=False)
    print('Building daily, content and audience marts',flush=True)
    con.execute((ROOT/'sql/02_marts.sql').read_text())
    frames={table:con.execute(f'SELECT * FROM {table}').fetchdf() for table in EXPORTS}
    for table,df in frames.items(): df.to_csv(output_dir/f'{table}.csv',index=False)
    weeks=frames['weekly_comparison'].set_index('period')
    factors=['active_users','exposures_per_user','seconds_per_exposure']
    before={k:float(weeks.loc['baseline',k]) for k in factors}
    after={k:float(weeks.loc['comparison',k]) for k in factors}
    contributions={k:v/3600 for k,v in shapley_product(before,after).items()}
    mix={}
    for period in ['baseline','comparison']:
        mix[period]={r.duration_band:(r.exposures,r.seconds_per_exposure)
                     for r in frames['duration_period'].itertuples() if r.period==period}
    mix_rows=mix_decomposition(mix['baseline'],mix['comparison'])
    pd.DataFrame(mix_rows).to_csv(output_dir/'duration_mix_decomposition.csv',index=False)
    returns=con.execute('''SELECT horizon,count(*) FILTER (WHERE eligible) eligible_users,
      count(*) FILTER (WHERE eligible AND returned) returned_users FROM return_observations GROUP BY horizon ORDER BY horizon''').fetchdf()
    returns['return_rate']=returns.returned_users/returns.eligible_users.replace(0,float('nan'))
    intervals=[wilson(int(r.returned_users),int(r.eligible_users)) for r in returns.itertuples()]
    returns['wilson_lower']=[v[0] for v in intervals];returns['wilson_upper']=[v[1] for v in intervals]
    returns.to_csv(output_dir/'pooled_return.csv',index=False)
    summary=con.execute('''SELECT count(*) exposures,count(DISTINCT user_id) users,
      sum(watch_seconds)/3600 watch_hours,sum(capped_watch_seconds)/3600 capped_watch_hours,
      avg(watch_seconds) seconds_per_exposure, avg(derived_long_view) long_view_rate,
      avg(completed) completion_rate FROM standard_events''').fetchdf().to_dict('records')[0]
    tail=con.execute('''WITH threshold AS (SELECT quantile_cont(watch_seconds,.99) p99 FROM standard_events)
      SELECT sum(least(watch_seconds,p99))/sum(watch_seconds) AS p99_winsorized_watch_share,
      sum(CASE WHEN watch_seconds>p99 THEN watch_seconds ELSE 0 END)/sum(watch_seconds) AS above_p99_watch_share
      FROM standard_events CROSS JOIN threshold''').fetchdf().to_dict('records')[0]
    delta=float(weeks.loc['comparison','watch_hours']-weeks.loc['baseline','watch_hours'])
    # Unknown duration is excluded from duration-based metrics, but quantify the
    # consequence for watch-time trends instead of hiding the excluded activity.
    unknown=con.execute("""SELECT CASE WHEN event_date BETWEEN DATE '2022-04-08' AND DATE '2022-04-14'
      THEN 'baseline' ELSE 'comparison' END AS period, count(*) exposures,
      sum(play_time_ms)/3600000.0 AS watch_hours FROM classified
      WHERE duration_ms=0 AND play_time_ms>=0 AND is_rand=0 AND
      (event_date BETWEEN DATE '2022-04-08' AND DATE '2022-04-14' OR event_date BETWEEN DATE '2022-04-29' AND DATE '2022-05-05')
      GROUP BY period""").fetchdf().set_index('period')
    sensitivities=[]
    for label,col in [('raw_watch','watch_hours'),('duration_capped','capped_watch_hours')]:
        v0=float(weeks.loc['baseline',col]);v1=float(weeks.loc['comparison',col])
        sensitivities.append({'definition':label,'baseline_hours':v0,'comparison_hours':v1,'change_pct':(v1/v0-1)*100})
    v0=float(weeks.loc['baseline','watch_hours']+unknown.loc['baseline','watch_hours'])
    v1=float(weeks.loc['comparison','watch_hours']+unknown.loc['comparison','watch_hours'])
    sensitivities.append({'definition':'including_unknown_duration','baseline_hours':v0,'comparison_hours':v1,'change_pct':(v1/v0-1)*100})
    pd.DataFrame(sensitivities).to_csv(output_dir/'watch_sensitivity.csv',index=False)
    mix_delta=float(weeks.loc['comparison','seconds_per_exposure']-weeks.loc['baseline','seconds_per_exposure'])
    checks={
      'published_archive_counts':counts['raw']==11713045+43028,
      'daily_exposure_reconciliation':int(frames['daily'].exposures.sum())==counts['standard_events'],
      'duration_exposure_reconciliation':int(frames['duration_segments'].exposures.sum())==counts['standard_events'],
      'user_day_uniqueness':con.execute('SELECT count(*) FROM (SELECT user_id,event_date FROM user_day GROUP BY ALL HAVING count(*)>1)').fetchone()[0]==0,
      'full_31_day_coverage':len(frames['daily'])==31,
      'seven_days_each_comparison':bool((frames['weekly_comparison'].observed_days==7).all()),
      'policy_file_consistency':quality['policy_file_mismatches']==0,
      'watch_identity':abs(float(frames['daily'].watch_hours.sum())-summary['watch_hours'])<1e-6,
      'shapley_reconciliation':abs(sum(contributions.values())-delta)<1e-6,
      'mix_reconciliation':abs(sum(r['mix_seconds']+r['within_seconds'] for r in mix_rows)-mix_delta)<1e-8,
      'censoring_denominators':bool((returns.returned_users<=returns.eligible_users).all()),
      'audience_join_cardinality':int(frames['audience_segments'].users.sum())==con.execute("SELECT count(DISTINCT user_id) FROM user_day WHERE event_date BETWEEN DATE '2022-04-08' AND DATE '2022-04-14'").fetchone()[0],
    }
    result={'dataset':'KuaiRand-1K','window':['2022-04-08','2022-05-08'],
      'primary_population':'Valid deduplicated standard-policy logged exposures',
      'summary':summary,'tail_sensitivity':tail,'weekly_watch_change_hours':delta,
      'weekly_watch_change_pct':delta/float(weeks.loc['baseline','watch_hours'])*100,
      'shapley_hours':contributions,'mix_change_seconds':mix_delta,
      'mix_component_seconds':sum(r['mix_seconds'] for r in mix_rows),
      'within_component_seconds':sum(r['within_seconds'] for r in mix_rows),
      'pooled_return':returns.to_dict('records'),'checks':checks,'quality':quality}
    (output_dir/'results.json').write_text(json.dumps(result,indent=2,default=str,allow_nan=False)+'\n')
    (output_dir/'data_provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    con.close()
    if not all(checks.values()):raise ValueError(f'Failed reconciliation checks: {checks}')
    print(json.dumps({'status':'PASS','checks':len(checks),'summary':summary},indent=2),flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw-dir',type=Path,default=ROOT/'data/raw')
    p.add_argument('--output-dir',type=Path,default=ROOT/'reports')
    a=p.parse_args();run(a.raw_dir,a.output_dir)
