# Metric contracts

The primary population is valid, exactly deduplicated **standard-policy** logged exposures in KuaiRand-1K, April 8–May 8, 2022. The random-policy file is ingested for lineage and quality auditing; it is not pooled into the primary engagement trends. Each row is a logged exposure, not necessarily a video play or a distinct person.

| Metric | Numerator / calculation | Denominator / grain | Interpretation |
|---|---|---|---|
| Watch hours | Sum `play_time_ms / 3,600,000` | Period | Recorded viewing, including extended/repeated playback |
| Capped watch hours | Sum `min(play_time_ms, duration_ms) / 3,600,000` | Same exposures | Sensitivity analysis; not a correction to ground truth |
| Active users | Distinct `user_id` with a valid standard exposure | Calendar day or comparison week | Logged exposure activity, including zero-watch exposures |
| Exposures per user | Count exposures / distinct users | Same period | Frequency factor; never sum daily distinct users for weekly users |
| Mean seconds per exposure | Sum watch seconds / exposure count | Exposure | Includes zero-watch exposures |
| Derived long-view rate | `play_time_ms >= min(duration_ms, 18,000)` | Valid exposures | Explicit engagement proxy; not a business-defined quality-hour KPI |
| Completion rate | Count `play_time_ms >= duration_ms` | Valid exposures with positive duration | At least one duration's worth of viewing; replay may exceed one |
| D1 / D7 return | Users with a valid standard exposure exactly 1 / 7 days after first observed day | Users whose first day + horizon is within the data window | First-observed cohort; **not signup retention or subscriber churn** |
| Audience next-week return | Early-week users active Apr 15–21 | Users active Apr 8–14, grouped by early watch-time quartile | Observational association, not the effect of increasing watch time |

## Windows and attribution

- Use the source `date` for calendar days. Audit consistency with epoch milliseconds plus UTC+8; do not silently reinterpret timestamps in the local computer timezone.
- Compare Apr 8–14 with Apr 29–May 5: two complete Friday–Thursday windows. These are descriptive windows specified in SQL, not optimized for a favorable result. The data window ends May 8.
- Weekly watch hours = active users × exposures per user × mean watch seconds / 3,600. Exact Shapley decomposition averages all six factor-update orders and reconciles to the observed difference. It attributes an arithmetic difference, **not causality**.
- Separate duration-mix and within-band changes in mean watch seconds using the symmetric two-factor decomposition. Duration bands are not genres or semantic content categories. Reject absent segment support rather than invent means.
- Quartiles use only Apr 8–14 watch time. User IDs break ties deterministically. Outcomes begin Apr 15. Full-month statistical video features and user activity labels are deliberately excluded because their temporal availability is not established.

## Quality policy and limitations

- Verify the official archive MD5, then SHA-256 for each extracted input. Fail on unexpected schema or changed inputs.
- Remove exact duplicates across all source fields. Preserve repeated user/video observations with different timestamps or feedback. Audit candidate-key collisions separately; there is no official event ID.
- Exclude malformed IDs/dates, negative watch time, nonpositive duration and invalid primary flags from the main metrics. Publish exclusion counts. Watch time greater than duration is retained; publish capped and 99th-percentile sensitivity.
- `is_click` has different meanings in one-column and two-column interfaces. Do not label its pooled mean “CTR.” The project does not infer interface identities from undocumented `tab` codes.
- Compare recorded `long_view` with the documented formula. Publish mismatch counts; the headline proxy consistently uses the explicit formula.
- The sample contains 1,000 selected platform users and left-truncated behavior. High observed return does not generalize to new users, all Kuaishou users, or Disney subscribers. Nonreturn means no observed qualifying exposure, not confirmed churn.
- Wilson intervals use one Bernoulli outcome per eligible user and are descriptive. They do not correct selection bias or establish population representativeness.
- Raw logs, user IDs, and per-user marts remain local. Only aggregates and source-file hashes are published.
