"""Build the stakeholder report, figures, README and executed companion notebook."""
from pathlib import Path
import contextlib
import html
import io
import json
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import nbformat
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
R=ROOT/'reports'

def main():
    r=json.loads((R/'results.json').read_text());s=r['summary'];q=r['quality']
    daily=pd.read_csv(R/'daily.csv');daily.event_date=pd.to_datetime(daily.event_date)
    segments=pd.read_csv(R/'duration_segments.csv');audience=pd.read_csv(R/'audience_segments.csv')
    sensitivity=pd.read_csv(R/'watch_sensitivity.csv')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.titleweight':'bold','axes.labelcolor':'#374151'})
    fig,axs=plt.subplots(2,2,figsize=(13,8.8),layout='constrained')
    teal='#087f8c';orange='#c46335';navy='#153447'
    ax=axs[0,0];ax.plot(daily.event_date,daily.watch_hours,color=teal,lw=2,label='Recorded hours')
    ax.plot(daily.event_date,daily.capped_watch_hours,color=navy,lw=1.5,linestyle='--',label='Duration-capped')
    ax.set_title('01  Watch time across the observation window',loc='left',pad=14)
    ax.set_ylabel('Watch hours / day');ax.xaxis.set_major_locator(matplotlib.dates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%b %d'));ax.legend(frameon=False,fontsize=9)
    ax=axs[0,1];values=list(r['shapley_hours'].values());labels=['Active users','Exposures / user','Seconds / exposure']
    bars=ax.barh(labels,values,color=[teal if v>=0 else orange for v in values]);ax.axvline(0,color='#9ca3af',lw=.8)
    for bar,value in zip(bars,values):ax.text(value+(25 if value>=0 else -25),bar.get_y()+bar.get_height()/2,f'{value:+,.0f}',va='center',ha='left' if value>=0 else 'right',fontsize=10)
    ax.set_xlim(min(values)*1.65,max(values)*1.3);ax.set_xlabel('Contribution to change in weekly hours')
    ax.set_title('02  Frequency drives the increase',loc='left',pad=14)
    ax=axs[1,0];x=range(len(segments));ax.bar(x,segments.seconds_per_exposure,color=teal,width=.65)
    ax.set_xticks(list(x),[v.split(' | ')[1] for v in segments.duration_band]);ax.set_ylabel('Seconds per logged exposure')
    ax.set_xlabel('Video duration band');ax.set_title('03  Longer videos accumulate more watch time',loc='left',pad=14)
    ax=axs[1,1];ax.bar(['Q1\nLowest','Q2','Q3','Q4\nHighest'],audience.avg_next_active_days,color=[teal]*4,width=.6)
    ax.set_ylim(0,7);ax.set_ylabel('Average active days in following week');ax.set_xlabel('Prior-week watch-time quartile')
    ax.set_title('04  Early engagement is associated with return',loc='left',pad=14)
    for ax in axs.flat:ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('VIDEO ENGAGEMENT  /  KuaiRand-1K',ha='left',x=.02,fontsize=19,color=navy,weight='bold')
    fig.savefig(R/'overview.png',dpi=160,facecolor='white');plt.close(fig)
    d7=next(x for x in r['pooled_return'] if x['horizon']==7)
    findings=[
      f"Watch time increased {r['weekly_watch_change_pct']:.2f}% between the two complete comparison weeks. Exposure frequency contributed {r['shapley_hours']['exposures_per_user']:+,.0f} hours, while seconds per exposure contributed {r['shapley_hours']['seconds_per_exposure']:+,.0f} hours. More activity did not mean deeper viewing per exposure.",
      f"Mean seconds per exposure fell {abs(r['mix_change_seconds']):.3f} seconds. The duration-mix component was {r['mix_component_seconds']:+.3f} seconds and the within-band component was {r['within_component_seconds']:+.3f} seconds. This is an arithmetic decomposition, not causal attribution.",
      f"The highest prior-week watch-time quartile averaged {audience.iloc[-1].avg_next_active_days:.2f} active days in the next week, versus {audience.iloc[0].avg_next_active_days:.2f} in the lowest quartile. Both groups had high next-week return; active-day intensity is more informative here than a binary returned/not-returned label.",
      f"Exact-day D7 return was {d7['return_rate']:.2%} ({d7['returned_users']}/{d7['eligible_users']} eligible users). First-observed cohorts in this selected sample are not signup cohorts, and nonreturn is not confirmed churn."
    ]
    quality_rows=[
      ('Input lineage',f"{q['counts']['raw']:,} rows; archive MD5 and per-file SHA-256 verified",'Three official logs; no synthetic main dataset'),
      ('Exact duplication',f"{q['exact_duplicate_rows_removed']:,} rows removed",'All source columns compared; repeated viewing preserved'),
      ('Unknown duration',f"{q['zero_duration_rows']:,} zero-duration rows",f"Excluded from primary duration metrics; {q['zero_duration_standard_watch_hours']:,.1f} standard watch hours measured separately"),
      ('Long-view semantics',f"{q['long_view_definition_mismatches']:,} formula/label mismatches",'Published proxy uses the explicit duration/18-second formula'),
      ('Date alignment',f"{q['utc_plus_8_date_mismatches']:,} source-date / UTC+8 disagreements",'Use source calendar dates consistently; upstream cause is unconfirmed'),
      ('Candidate event key',f"{q['candidate_key_duplicate_excess']:,} excess rows on candidate key",'No official event ID; conflicting feedback rows are retained'),
      ('Playback beyond duration',f"{q['extended_play_rows']:,} observations",'Retained; compare recorded, capped and tail-sensitive definitions'),
    ]
    rows=''.join('<tr>'+''.join(f'<td>{html.escape(v)}</td>' for v in row)+'</tr>' for row in quality_rows)
    kpis=[(f"{q['counts']['raw']/1e6:.2f}M",'Source log rows'),(f"{s['exposures']/1e6:.2f}M",'Eligible standard exposures'),
          (f"{s['watch_hours']:,.0f}",'Recorded watch hours'),(f"{r['weekly_watch_change_pct']:+.2f}%",'Comparison-week change')]
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video Engagement Analytics | Ricky Sun</title><style>
:root{color:#183447;background:#f4f3ef;font-family:system-ui,-apple-system,Segoe UI,sans-serif}*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:52px 32px}header{border-top:5px solid #087f8c;padding-top:20px}.eyebrow{font-size:12px;letter-spacing:2px;font-weight:700;color:#087f8c}h1{font-size:46px;line-height:1.12;letter-spacing:-1.5px;margin:18px 0}h2{font-size:25px;margin-top:42px}.lead{max-width:820px;font-size:18px;line-height:1.65;color:#526570}.meta{font-size:13px;color:#526570}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin:32px 0}.kpi{border-top:1px solid #a9b7bc;padding:17px 0}.kpi b{display:block;font-size:34px}.kpi span{font-size:12px;color:#526570}.panel{background:white;border:1px solid #dae0df;padding:25px;margin:22px 0}.panel img{width:100%;height:auto}li,p{line-height:1.7}li{padding:5px 0}.note{border-left:4px solid #c46335;background:#fff8f0;padding:15px 20px;font-size:14px}table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;padding:12px 10px;border-bottom:1px solid #dce2e2;vertical-align:top}th{background:#e9efee}a{color:#087f8c}select{font:inherit;padding:7px 12px;margin-left:10px;border:1px solid #a9b7bc;background:white}svg{width:100%;height:auto}footer{border-top:1px solid #a9b7bc;margin-top:45px;padding-top:20px;font-size:12px;color:#526570}@media(max-width:700px){main{padding:28px 18px}h1{font-size:34px}.kpis{grid-template-columns:repeat(2,1fr)}.kpi b{font-size:28px}.panel{padding:12px}table{font-size:11px}td,th{padding:8px 5px}}
</style><main><header><div class="eyebrow">RICKY SUN · INDEPENDENT ANALYTICS PROJECT</div><h1>More watch time.<br>What actually changed?</h1><p class="lead">A reproducible analysis of viewing intensity, content duration and audience return using real short-video recommendation logs.</p><p class="meta">KuaiRand-1K · April 8–May 8, 2022 · SQL + Python + DuckDB · 1,000 sampled users</p></header>'''
    page+='<div class="kpis">'+''.join(f'<div class="kpi"><b>{v}</b><span>{label}</span></div>' for v,label in kpis)+'</div>'
    page+='<div class="note">These are Kuaishou short-video observations. They do not measure Disney subscribers, new-user retention or causal business impact. Comparison windows: Apr 8–14 and Apr 29–May 5.</div>'
    page+='<h2>What the evidence says</h2><ol>'+''.join(f'<li>{html.escape(v)}</li>' for v in findings)+'</ol>'
    page+='<div class="panel"><img src="overview.png" alt="Four charts showing daily watch hours, factor contributions, watch seconds by video duration, and next-week active days by prior engagement quartile"></div>'
    page+='<h2>Explore the daily trend</h2><div class="panel"><label for="metric">Metric</label><select id="metric"><option value="watch_hours">Recorded watch hours</option><option value="capped_watch_hours">Duration-capped watch hours</option><option value="active_users">Active users</option><option value="seconds_per_exposure">Seconds per exposure</option></select><svg id="trend" viewBox="0 0 1000 285" role="img" aria-label="Daily trend for selected metric"></svg><p class="meta" id="trend-note"></p></div>'
    readable_sensitivity=sensitivity.rename(columns={'definition':'Watch-time definition','baseline_hours':'Baseline hours','comparison_hours':'Comparison hours','change_pct':'Change (%)'}).copy()
    readable_sensitivity['Watch-time definition']=readable_sensitivity['Watch-time definition'].replace({'raw_watch':'Recorded viewing','duration_capped':'Capped at video duration','including_unknown_duration':'Including unknown duration'})
    page+='<h2>How robust is the watch-time trend?</h2>'+readable_sensitivity.round(3).to_html(index=False,border=0)
    page+=f'<p>Removing the amount above the 99th-percentile watch-time threshold retains {r["tail_sensitivity"]["p99_winsorized_watch_share"]:.2%} of total watch time. Capping at video duration retains {s["capped_watch_hours"]/s["watch_hours"]:.2%}. These are sensitivity definitions, not claims that extended playback is erroneous.</p>'
    page+='<h2>Data quality and unresolved limitations</h2><table><thead><tr><th>Check</th><th>Evidence</th><th>Treatment / implication</th></tr></thead><tbody>'+rows+'</tbody></table>'
    page+='<h2>Recommended next investigation</h2><p>Prioritize the decline in seconds per exposure. Review duration-mix changes alongside within-band viewing depth and recommendation scenarios before proposing a content intervention. The high binary return rates suggest using active days or viewing intensity to distinguish these existing-user groups. A controlled experiment would be needed to establish whether a content change improves engagement or retention.</p>'
    page+='<h2>Reproduce and inspect</h2><p><a href="https://github.com/RickySun-hub/video-engagement-analytics">Code and README</a> · <a href="results.json">Results and QA checks</a> · <a href="../docs/metric_contracts.md">Metric contracts</a> · <a href="pooled_return.csv">Return denominators</a></p>'
    page+='<footer>Source: <a href="https://kuairand.com/">KuaiRand</a>, Gao et al., CIKM 2022. Derived reports: CC BY-SA 4.0. No raw user logs are published. The SQL population and all exclusions are recorded in the repository.</footer></main>'
    records=daily.assign(event_date=daily.event_date.dt.strftime('%Y-%m-%d')).to_dict('records')
    page+='<script>const days='+json.dumps(records)+';'+'''
function draw(){const field=document.getElementById('metric').value,values=days.map(d=>d[field]),max=Math.max(...values)*1.08;const x=i=>70+i*895/(days.length-1),y=v=>235-v/max*210;let body='';for(let i=0;i<=4;i++){const v=max*i/4;body+=`<line x1="70" y1="${y(v)}" x2="965" y2="${y(v)}" stroke="#e0e6e5"/><text x="60" y="${y(v)+4}" text-anchor="end" font-size="12" fill="#526570">${v.toFixed(v<50?1:0)}</text>`}body+=`<polyline points="${values.map((v,i)=>`${x(i)},${y(v)}`).join(' ')}" fill="none" stroke="#087f8c" stroke-width="3"/>`;days.forEach((d,i)=>{body+=`<circle cx="${x(i)}" cy="${y(values[i])}" r="3" fill="#087f8c"><title>${d.event_date}: ${values[i].toFixed(2)}</title></circle>`;if(i%7===0||i===days.length-1)body+=`<text x="${x(i)}" y="265" text-anchor="middle" font-size="12" fill="#526570">${d.event_date.slice(5)}</text>`});document.getElementById('trend').innerHTML=body;document.getElementById('trend-note').textContent='31 daily observations. Hover over a point for the date and value. Definitions use valid standard-policy exposures.'}document.getElementById('metric').addEventListener('change',draw);draw();</script>'''
    (R/'index.html').write_text(page,encoding='utf-8')
    readme=f'''# Video Engagement Analytics

**Why did watch time increase, and what does viewing behavior tell us about audience return?**

An independent portfolio project using real **KuaiRand-1K** short-video logs. SQL builds event, daily and user-day marts; Python decomposes engagement changes, validates denominators and generates an interactive HTML report. This is observational product analytics, not a deployed business intervention.

![Engagement analysis overview](reports/overview.png)

## Findings

'''+''.join(f'- {f}\n' for f in findings)+f'''
## What I built

- A checksum-verified ingestion pipeline for **{q['counts']['raw']:,} events**, with exact duplicate auditing, domain checks and explicitly defined exposure populations.
- DuckDB SQL marts for daily KPIs, video-duration segments, recommendation scenarios, censored D1/D7 return and temporally separated audience segments.
- An exact three-factor Shapley decomposition of watch hours and a duration-mix versus within-band decomposition of average viewing time, both reconciled to observed changes.
- A stakeholder report with an interactive daily metric selector, aggregate CSVs, an executed companion notebook, and tests for censoring, replay, thresholds, join cardinality and arithmetic reconciliation.

## Reproduce

Python 3.12 and `curl` are required. The official archive is 1.14 GB; allow about 5 GB of free disk space for the archive, extracted logs and DuckDB working files. The local run uses four DuckDB threads and a 2 GB memory limit. No API credentials or paid services are needed.

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/fetch_data.py
python scripts/analyze.py
python scripts/render_report.py
python -m unittest discover -s tests -v
python scripts/verify_artifacts.py
```

Open `reports/index.html` in a browser. To inspect only the published report, downloading the dataset is unnecessary. To query the local marts, open `data/processed/engagement.duckdb` with DuckDB. Raw and user-level data stays git-ignored.

## Evidence and quality

| Check | Result |
|---|---:|
| Official source rows | {q['counts']['raw']:,} |
| Exact duplicate rows removed | {q['exact_duplicate_rows_removed']:,} |
| Zero-duration records excluded from duration-based primary metrics | {q['zero_duration_rows']:,} |
| Eligible standard-policy exposures | {s['exposures']:,} |
| Sampled users represented | {s['users']:,} |
| Formula / recorded long-view mismatches, all valid policies | {q['long_view_definition_mismatches']:,} |
| Source-date / UTC+8 disagreements, all valid policies | {q['utc_plus_8_date_mismatches']:,} |
| Data reconciliation checks | {len(r['checks'])}, all passed |

The unknown-duration records contain {q['zero_duration_standard_watch_hours']:,.1f} standard-policy watch hours. Their impact is visible in [watch sensitivity](reports/watch_sensitivity.csv). Recorded watch hours, duration-capped watch hours and the explicit long-view proxy answer different questions. No global CTR is reported because the source `is_click` semantics vary by interface. Source calendar dates are retained; date disagreements and feedback-label discrepancies remain upstream uncertainties.

## Read the work

| Artifact | Purpose |
|---|---|
| [Metric contracts](docs/metric_contracts.md) | Grain, windows, numerators, denominators and boundaries |
| [Cleaning SQL](sql/01_clean.sql) | Exact deduplication, validity rules, replay treatment |
| [Analytical SQL](sql/02_marts.sql) | KPIs, content segments, returns and audience features |
| [Analysis notebook](notebooks/engagement_analysis.ipynb) | Executed walkthrough of published results and methods |
| [Results and checks](reports/results.json) | Machine-readable outputs, exclusions and validations |
| [Data provenance](reports/data_provenance.json) | Official source, archive MD5 and extracted-file SHA-256 |

## Interpretation limits

The source covers 1,000 sampled Kuaishou users during a 2022 observation window. First observation is not signup, and absent activity is not proven churn. This is not Disney customer data, a subscription experiment or evidence of increased revenue. Quartile comparisons are associations with no causal interpretation. Full-month statistical features are not used as predictors because they can leak future outcomes. Duration bands describe length, not genre. Arithmetic contributions explain the observed KPI difference; they are not estimates of treatment effects.

## Source and license

[KuaiRand](https://kuairand.com/), Gao et al., CIKM 2022, [DOI 10.1145/3511808.3557624](https://doi.org/10.1145/3511808.3557624). The official [Zenodo archive](https://zenodo.org/records/10439422) is downloaded and verified locally. Original code: MIT. Data-derived reports and figures: CC BY-SA 4.0; see [DATA_LICENSE.md](DATA_LICENSE.md).
'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')
    cells=[nbformat.v4.new_markdown_cell('# Video Engagement Analytics\n\nExecuted walkthrough of the actual aggregate outputs. Run the scripts in the README to regenerate the underlying SQL marts. No user-level records are embedded.'),
      nbformat.v4.new_code_cell("from pathlib import Path\nimport json, pandas as pd\nROOT = Path.cwd() if (Path.cwd()/'reports/results.json').exists() else Path.cwd().parent\nresult = json.loads((ROOT/'reports/results.json').read_text())\nprint(json.dumps(result['summary'], indent=2))"),
      nbformat.v4.new_markdown_cell('## Quality before interpretation\nExact duplicates are removed. Zero-duration exposures cannot support completion metrics; sensitivity analyses quantify their watch-time effect. Upstream date and feedback discrepancies are retained as caveats.'),
      nbformat.v4.new_code_cell("q=result['quality']\nprint(json.dumps({k:q[k] for k in ['counts','exact_duplicate_rows_removed','zero_duration_rows','long_view_definition_mismatches','utc_plus_8_date_mismatches']},indent=2))"),
      nbformat.v4.new_markdown_cell('## Watch-hour decomposition\nThe three factors use the same weekly population. Contributions are arithmetic, not causal.'),
      nbformat.v4.new_code_cell("print(pd.read_csv(ROOT/'reports/weekly_comparison.csv').to_string(index=False))\nprint(result['shapley_hours'])\nassert abs(sum(result['shapley_hours'].values())-result['weekly_watch_change_hours'])<1e-6"),
      nbformat.v4.new_markdown_cell('## Return and audience behavior\nD7 has a user-level eligible denominator and an exact-day outcome. Prior-week quartiles use no future data.'),
      nbformat.v4.new_code_cell("print(pd.read_csv(ROOT/'reports/pooled_return.csv').to_string(index=False))\nprint(pd.read_csv(ROOT/'reports/audience_segments.csv').to_string(index=False))"),
      nbformat.v4.new_markdown_cell('## Sensitivity and checks'),
      nbformat.v4.new_code_cell("print(pd.read_csv(ROOT/'reports/watch_sensitivity.csv').to_string(index=False))\nassert all(result['checks'].values())\nprint(f\"{len(result['checks'])} reconciliation checks passed\")")]
    # Execute these lightweight inspection cells against the generated artifacts.
    namespace={};execution=0
    import os
    previous=Path.cwd();os.chdir(ROOT)
    try:
        for cell in cells:
            if cell.cell_type!='code':continue
            execution+=1;capture=io.StringIO()
            with contextlib.redirect_stdout(capture):exec(cell.source,namespace)
            cell.execution_count=execution
            cell.outputs=[nbformat.v4.new_output('stream',name='stdout',text=capture.getvalue())]
    finally:os.chdir(previous)
    nb=nbformat.v4.new_notebook(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}})
    nbformat.validate(nb);(ROOT/'notebooks').mkdir(exist_ok=True)
    nbformat.write(nb,ROOT/'notebooks/engagement_analysis.ipynb')
    print('Created report, overview figure, README and executed notebook')

if __name__=='__main__':main()
