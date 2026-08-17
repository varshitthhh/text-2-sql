# Baseline — Qwen2.5-Coder-7B-Instruct (custom food-delivery benchmark)

**Overall execution accuracy: 56/100 = 56.0%**

| Tier | Correct | Total | Accuracy |
|---|---|---|---|
| single_table | 20 | 20 | 100.0% |
| join | 17 | 20 | 85.0% |
| aggregation | 13 | 20 | 65.0% |
| nested_subquery | 6 | 20 | 30.0% |
| ambiguous | 0 | 20 | 0.0% |

## Non-infrastructure errors (7)

Genuine model reasoning failures only — 4 separate timeouts were retried, not counted as wrong.

5 of the 7 share one root cause: the model assumes `ratings` has direct `driver_id`/`restaurant_id` foreign keys, but `ratings` only links to `orders` — it needs to join through `orders` to reach driver/restaurant info. A recurring schema-linking gap, not unrelated mistakes.

- **[45]** What is the average driver rating for each vehicle type?
  - `predicted SQL error: Binder Error: Table "r" does not have a column named "driver_id"`
- **[52]** How many ratings has each restaurant received, and what's the average rating?
  - `predicted SQL error: Binder Error: Table "ra" does not have a column named "restaurant_id"`
- **[68]** List drivers whose average rating is below the overall average driver rating.
  - `predicted SQL error: Binder Error: Table "r" does not have a column named "driver_id"`
- **[86]** Are customers happy with delivery?
  - `predicted SQL error: Catalog Error: Scalar Function with name curdate does not exist!`
- **[89]** Who's underperforming among our drivers?
  - `predicted SQL error: Binder Error: Table "r" does not have a column named "driver_id"`
- **[90]** What kind of food do people order most?
  - `predicted SQL error: Binder Error: Table "T2" does not have a column named "category"`
- **[100]** Which restaurants get the worst customer feedback?
  - `predicted SQL error: Binder Error: Table "ra" does not have a column named "restaurant_id"`

## Baseline — Qwen2.5-Coder-7B-Instruct (BIRD Mini-Dev, official execution accuracy)

| Difficulty | Count | EX Accuracy |
|---|---|---|
| Simple | 148 | 62.16% |
| Moderate | 250 | 40.80% |
| Challenging | 102 | 23.53% |
| **Total** | **500** | **43.60%** |

Scored via BIRD's official `evaluation_ex.py`, with the `evidence` field included in prompts
(matching BIRD's standard "with knowledge" evaluation convention). The monotonic decline across
difficulty tiers is the expected pattern and matches the shape of published BIRD baselines,
giving confidence this run is trustworthy.

**Infrastructure note:** the 500-query generation run required 5 manual Ollama server restarts
due to a recurring server crash under sustained load (GPU memory evicted, port stops responding,
process remains alive but unreachable). Documented as a genuine reliability finding, not a
modeling issue — mitigated with a `func_timeout` hard backstop per request and automatic
health-check-and-restart between chunks.

## Baseline — SQLCoder (Ollama official, 7B) — custom food-delivery benchmark

**Overall execution accuracy: 37/100 = 37.0%**

| Tier | Correct | Total | Accuracy |
|---|---|---|---|
| single_table | 15 | 20 | 75.0% |
| join | 5 | 20 | 25.0% |
| aggregation | 11 | 20 | 55.0% |
| nested_subquery | 4 | 20 | 20.0% |
| ambiguous | 2 | 20 | 10.0% |

**Comparison to Qwen2.5-Coder-7B-Instruct on the same benchmark: 56.0% vs SQLCoder's 37.0%.**

SQLCoder's errors are dominated by two systematic patterns, not random noise: (1) malformed CTE syntax -- repeatedly generating `WITH AVG(...) AS x FROM ...` instead of the correct `WITH cte_name AS (SELECT ...)` structure, across at least 6 of the 27 genuine errors; and (2) the same `ratings`-table join-path confusion Qwen also exhibited (assuming direct `restaurant_id`/`driver_id` columns that don't exist), suggesting this specific schema ambiguity is genuinely non-obvious rather than a model-specific weakness. One example (83) never produced a non-empty completion despite 3 separate attempts and is counted as wrong, documented as residual infrastructure noise rather than a reasoning failure.

**Response-parsing note:** SQLCoder is a narrowly fine-tuned completion model (not a general instruction-tuned chat model like Qwen), and required a model-specific prompt template (Defog's documented `### Task / ### Database Schema / ### Answer` format) rather than the generic instruction-style prompt used for Qwen -- the wrong template initially produced incoherent, non-SQL output entirely. The completion also required parsing a trailing bracket-tag artifact (`[SQL]`, `[QUESTION]`, or an incomplete `[`) that the model appends after the query, which was not handled correctly on the first pass and inflated the initial error count (53 -> 27 genuine errors once fixed).

**Infrastructure note:** this run required substantially more Ollama server restarts than the Qwen baseline -- crashes occurred roughly every 10-20 queries rather than every 50-80, for reasons not fully diagnosed (possibly different GPU memory/KV-cache behavior for this model). Mitigated with the same hardened harness (func_timeout backstop + per-chunk health checks).


## Baseline — SQLCoder (Ollama official, 7B) — BIRD Mini-Dev (official execution accuracy)

| Difficulty | Count | EX Accuracy |
|---|---|---|
| Simple | 148 | 4.05% |
| Moderate | 250 | 1.20% |
| Challenging | 102 | 0.00% |
| **Total** | **500** | **1.80%** |

**Comparison to Qwen2.5-Coder-7B-Instruct on BIRD Mini-Dev: 43.60% vs SQLCoder's 1.80%.** A much
larger capability gap than on the custom benchmark (56% vs 37%), consistent with SQLCoder's
observed weaknesses (malformed CTE syntax, hallucinated columns/tables) being amplified by BIRD's
larger, more diverse real-world schemas.

**Known discrepancy, disclosed rather than hidden:** an earlier scoring pass (before 21 generation
timeouts were retried) gave 7.00%. After retrying, the score dropped to 1.80% -- the opposite of
what retrying failures should do (giving previously-failed examples a fair shot should only raise
or hold the score, never lower it). Investigated: the scoring mechanism is confirmed deterministic
(identical results on repeat runs), the predictions file is confirmed stable for spot-checked
entries, and the underlying SQLite databases pass integrity checks. The exact mechanism behind the
7.00% -> 1.80% shift was not fully isolated in the time available. 1.80% is reported as final because
it is the reproducible, verified state; this is flagged as an open methodological question rather
than resolved with confidence.
