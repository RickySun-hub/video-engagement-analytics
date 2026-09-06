CREATE OR REPLACE TABLE daily AS
SELECT event_date, count(*) AS exposures, count(DISTINCT user_id) AS active_users,
 sum(watch_seconds)/3600 AS watch_hours,
 sum(capped_watch_seconds)/3600 AS capped_watch_hours,
 avg(watch_seconds) AS seconds_per_exposure,
 count(*)::DOUBLE/count(DISTINCT user_id) AS exposures_per_user,
 avg(derived_long_view) AS long_view_rate, avg(completed) AS completion_rate,
 avg((play_time_ms>duration_ms)::INTEGER) AS replay_or_extended_rate
FROM standard_events GROUP BY event_date ORDER BY event_date;

CREATE OR REPLACE TABLE duration_segments AS
SELECT duration_band, count(*) AS exposures, count(DISTINCT user_id) AS active_users,
 avg(watch_seconds) AS seconds_per_exposure,
 sum(watch_seconds)/3600 AS watch_hours,
 avg(derived_long_view) AS long_view_rate, avg(completed) AS completion_rate
FROM standard_events GROUP BY duration_band ORDER BY duration_band;

CREATE OR REPLACE TABLE scenario_segments AS
SELECT tab, count(*) AS exposures, count(DISTINCT user_id) AS active_users,
 sum(watch_seconds)/3600 AS watch_hours, avg(watch_seconds) AS seconds_per_exposure,
 avg(derived_long_view) AS long_view_rate
FROM standard_events GROUP BY tab ORDER BY tab;

-- Compare two complete Friday-Thursday weeks, not unequal or partial windows.
CREATE OR REPLACE TABLE comparison_events AS
SELECT *, CASE WHEN event_date BETWEEN DATE '2022-04-08' AND DATE '2022-04-14'
 THEN 'baseline' ELSE 'comparison' END AS period
FROM standard_events
WHERE event_date BETWEEN DATE '2022-04-08' AND DATE '2022-04-14'
 OR event_date BETWEEN DATE '2022-04-29' AND DATE '2022-05-05';

CREATE OR REPLACE TABLE weekly_comparison AS
SELECT period, min(event_date) AS start_date, max(event_date) AS end_date,
 count(DISTINCT event_date) AS observed_days, count(*) AS exposures,
 count(DISTINCT user_id) AS active_users,
 count(*)::DOUBLE/count(DISTINCT user_id) AS exposures_per_user,
 avg(watch_seconds) AS seconds_per_exposure,
 sum(watch_seconds)/3600 AS watch_hours,
 sum(capped_watch_seconds)/3600 AS capped_watch_hours
FROM comparison_events GROUP BY period ORDER BY period;

CREATE OR REPLACE TABLE duration_period AS
SELECT period, duration_band, count(*) AS exposures,
 avg(watch_seconds) AS seconds_per_exposure
FROM comparison_events GROUP BY period, duration_band ORDER BY period, duration_band;

-- One row per user and horizon; activity is exact-day, not any-day within horizon.
CREATE OR REPLACE TABLE return_observations AS
WITH first_seen AS (SELECT user_id, min(event_date) AS cohort_date FROM user_day GROUP BY user_id),
 horizons AS (SELECT unnest([1,7]) AS horizon),
 bounds AS (SELECT max(event_date) AS last_date FROM user_day)
SELECT f.user_id, cohort_date, horizon,
 cohort_date + horizon <= last_date AS eligible,
 d.user_id IS NOT NULL AS returned
FROM first_seen f CROSS JOIN horizons CROSS JOIN bounds
LEFT JOIN user_day d ON d.user_id=f.user_id AND d.event_date=f.cohort_date+horizon;

CREATE OR REPLACE TABLE cohort_return AS
SELECT cohort_date, horizon, count(*) AS cohort_users,
 count(*) FILTER (WHERE eligible) AS eligible_users,
 count(*) FILTER (WHERE eligible AND returned) AS returned_users,
 count(*) FILTER (WHERE eligible AND returned)::DOUBLE /
 nullif(count(*) FILTER (WHERE eligible),0) AS return_rate
FROM return_observations GROUP BY cohort_date,horizon ORDER BY cohort_date,horizon;

-- All segmentation features end Apr 14. Outcomes begin Apr 15; no full-month
-- user/video statistical features are used, because they leak future behavior.
CREATE OR REPLACE TABLE audience_observations AS
WITH features AS (
 SELECT user_id, sum(watch_seconds) AS early_watch_seconds FROM user_day
 WHERE event_date BETWEEN DATE '2022-04-08' AND DATE '2022-04-14' GROUP BY user_id
), quartiles AS (
 SELECT *, ntile(4) OVER (ORDER BY early_watch_seconds,user_id) AS engagement_quartile FROM features
), outcomes AS (
 SELECT user_id, count(*) AS next_active_days, sum(watch_seconds) AS next_watch_seconds
 FROM user_day WHERE event_date BETWEEN DATE '2022-04-15' AND DATE '2022-04-21' GROUP BY user_id
)
SELECT f.*, coalesce(next_active_days,0) AS next_active_days,
 coalesce(next_watch_seconds,0) AS next_watch_seconds, o.user_id IS NOT NULL AS returned_next_week
FROM quartiles f LEFT JOIN outcomes o USING(user_id);

CREATE OR REPLACE TABLE audience_segments AS
SELECT engagement_quartile, count(*) AS users,
 min(early_watch_seconds)/60 AS min_early_minutes, max(early_watch_seconds)/60 AS max_early_minutes,
 avg(early_watch_seconds)/60 AS avg_early_minutes,
 avg(next_active_days) AS avg_next_active_days,
 avg(next_watch_seconds)/60 AS avg_next_minutes,
 sum(returned_next_week::INTEGER) AS returned_users,
 avg(returned_next_week::INTEGER) AS next_week_return_rate
FROM audience_observations GROUP BY engagement_quartile ORDER BY engagement_quartile;
