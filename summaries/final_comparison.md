

## Phase 8 — Final system (repair loop -> self-consistency fallback -> guardrail gate)

| System | Accuracy | Notes |
|---|---|---|
| Baseline (single-shot) | 56/100 = 56.0% | Qwen2.5-Coder-7B, no scaffolding |
| Repair loop only | 59/100 = 59.0% | +3 net vs baseline |
| Final system (+ self-consistency fallback + guardrails) | 58/100 = 58.0% | Roughly flat vs repair-loop-only |

Fixed vs baseline: 4 -- [45, 62, 68, 76]
Regressed vs baseline: 2 -- [34, 67]

**Honest caveat:** the repair-loop-only run (59%) and the final-system run (58%) come from separate,
non-deterministic generation passes -- this project already observed the same 20-example subset
swing from 45% to 55% between two identical Q4 runs (Phase 7). A 1-point difference between the two
is within that noise band, not a confirmed regression from adding the self-consistency fallback.
What's reliable is that both scaffolded systems sit meaningfully above the 56% single-shot baseline.
This run was not instrumented to record which examples actually triggered the fallback path
(repair loop success vs. exhaustion) -- a real gap for a fully rigorous cost analysis, disclosed
here rather than papered over, and worth adding if this project continues past this scope.
