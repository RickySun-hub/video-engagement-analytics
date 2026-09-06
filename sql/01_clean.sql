-- The raw table retains every source column except file lineage in the duplicate key.
-- A repeated user/video is NOT a duplicate: repeats and replay are valid behaviors.
CREATE OR REPLACE TABLE deduplicated AS
SELECT DISTINCT * EXCLUDE (source_file) FROM raw;

CREATE OR REPLACE TABLE classified AS
SELECT *, try_strptime(CAST(date AS VARCHAR), '%Y%m%d')::DATE AS event_date,
 CASE WHEN user_id IS NULL OR video_id IS NULL OR time_ms IS NULL
   OR user_id < 0 OR video_id < 0 OR time_ms <= 0
   OR try_strptime(CAST(date AS VARCHAR), '%Y%m%d') IS NULL
   OR duration_ms IS NULL OR duration_ms <= 0
   OR play_time_ms IS NULL OR play_time_ms < 0
   OR is_rand IS NULL OR is_rand NOT IN (0,1)
   OR tab IS NULL OR tab NOT BETWEEN 0 AND 14
   OR long_view IS NULL OR long_view NOT IN (0,1)
 THEN FALSE ELSE TRUE END AS is_valid
FROM deduplicated;

CREATE OR REPLACE TABLE events AS
SELECT *, play_time_ms / 1000.0 AS watch_seconds,
 least(play_time_ms, duration_ms) / 1000.0 AS capped_watch_seconds,
 (play_time_ms >= least(duration_ms, 18000))::INTEGER AS derived_long_view,
 (play_time_ms >= duration_ms)::INTEGER AS completed,
 CASE WHEN duration_ms <= 10000 THEN '01 | <=10s'
      WHEN duration_ms <= 18000 THEN '02 | 10-18s'
      WHEN duration_ms <= 30000 THEN '03 | 18-30s'
      WHEN duration_ms <= 60000 THEN '04 | 30-60s'
      ELSE '05 | >60s' END AS duration_band
FROM classified WHERE is_valid;

CREATE OR REPLACE VIEW standard_events AS SELECT * FROM events WHERE is_rand=0;

CREATE OR REPLACE TABLE user_day AS
SELECT user_id, event_date, count(*) AS exposures, sum(watch_seconds) AS watch_seconds
FROM standard_events GROUP BY user_id, event_date;
