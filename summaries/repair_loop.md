

## Improvement 1 — Self-repair loop (LangGraph, single-agent) — custom benchmark

**Repair loop accuracy: 59/100 = 59.0%** (baseline: 56/100 = 56.0%, net +3)

- Fixed by repair loop: 8 examples -- [45, 62, 68, 69, 76, 86, 74, 75]
- Regressed (baseline correct, repair loop wrong): 5 -- [38, 41, 54, 61, 67]
- Net change: +3

**Nuance worth keeping**: in an isolated diagnostic test on the known baseline execution-errors
(45, 52, 68, 86, 89, 90, 100), the repair loop recovered from transient mistakes (52, 86: a one-off
wrong join key, fixed after seeing the error) but failed all 3 attempts on 45 and 100, both driven
by the same persistent, incorrect assumption that `ratings` has direct `restaurant_id`/`driver_id`
columns -- the error message alone didn't correct that belief in that run. In the full 100-example
run, 45 ended up fixed (generation isn't deterministic, so a different run can land differently),
while 100 remained wrong. The underlying point still holds: error-feedback repair reliably fixes
transient slips but is not a reliable fix for a persistent, incorrect schema assumption -- whether
any single instance of it gets fixed on a given run is closer to chance than to genuine correction.
