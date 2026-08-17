# Agentic Business Analytics / Text-to-SQL — Project Write-up

Solo build, Colab T4. Domain: food delivery (12-table custom schema) + BIRD Mini-Dev (500 examples,
11 real-world databases). Primary model: Qwen2.5-Coder-7B-Instruct (Ollama, 4-bit quantized).

## 1. Data & Evaluation

- **Custom benchmark**: 100 hand-authored NL->SQL pairs, stratified across 5 complexity tiers
  (single_table, join, aggregation, nested_subquery, ambiguous), verified deterministic and
  non-empty against a synthetic 12-table DuckDB database (customers, orders, restaurants, drivers,
  ratings, promotions, etc.).
- **BIRD Mini-Dev**: 500 official curated examples, scored via BIRD's own `evaluation_ex.py`
  (execution-accuracy, set-based comparison, no float tolerance -- kept as-is for comparability
  with published numbers).
- **Harness** (`code/harness.py`): SQLGlot-based SELECT-only validator + complexity classifier,
  DuckDB comparator with float tolerance (custom benchmark only), incremental JSONL logging with
  resume-skip for crash resilience.

## 2. Baseline Results

| Model | Custom benchmark | BIRD Mini-Dev |
|---|---|---|
| Qwen2.5-Coder-7B-Instruct | 56/100 = 56.0% | 43.60% (simple 62.16 / moderate 40.80 / challenging 23.53) |
| SQLCoder (Ollama official, 7B) | 37/100 = 37.0% | 1.80% (see note below) |

Qwen wins clearly on both benchmarks and was carried forward for all further phases. SQLCoder
required a model-specific prompt template (Defog's `### Task/### Database Schema/### Answer`
format, not a generic instruction prompt) and had a systematic weakness generating correct CTE
syntax. Its BIRD number has a documented, unresolved anomaly: an earlier scoring pass (before 21
generation timeouts were retried) gave 7.00%; after retrying, the reproducible score dropped to
1.80%. The scoring mechanism was confirmed deterministic and the databases passed integrity checks,
but the exact cause of the shift was not isolated in the time available -- disclosed here rather
than silently picking the more flattering number.

## 3. Failure Analysis (Qwen, custom benchmark)

| Category | Count |
|---|---|
| Correct | 56 |
| Silently wrong (executes, wrong result) | 37 |
| Execution error | 7 |
| Parse error | 0 |

Failure rate climbs sharply with complexity tier: single_table is 100% correct; ambiguous is 0%
correct with 80% silently-wrong. Two systematic patterns found, not random noise:
1. **Schema-linking confusion**: the model repeatedly assumes `ratings` has direct
   `restaurant_id`/`driver_id` columns, when it only links through `orders`. Recurring across
   multiple examples and observed in *both* Qwen and SQLCoder independently -- likely a genuinely
   non-obvious part of the schema design, not a model-specific weakness.
2. **Ambiguous-tier interpretation mismatches**: "best customers", "struggling restaurants", etc.
   admit multiple reasonable readings; the model's chosen interpretation often differs from the
   benchmark's chosen gold interpretation even when both are defensible.

Plots: `summaries/failure_categories_overall.png`, `summaries/failure_categories_by_tier.png`.

## 4. Improvements

**Repair loop (LangGraph, single-agent)**: `generate -> validate -> execute`, one conditional
retry edge, capped at 3 attempts. **59/100 (+3 net: 8 fixed, 5 regressed).** Recovers from
transient mistakes (a one-off wrong join key) but does not reliably correct a persistent, wrong
schema belief -- error-feedback repair is not the same as the model updating its understanding.
LangGraph was a deliberate learning choice, not an architectural necessity: a plain while-loop
would produce identical accuracy. Kept deliberately minimal -- no human-in-the-loop, no
checkpointer, no multi-agent, no complex branching.

**Self-consistency (majority vote, n=5)**: evaluated on a stratified 20-example subset (cost-bounded
per the roadmap, not run on the full 100). **11/20 (55.0%) vs. baseline's 10/20 (50.0%) on the same
subset, +1 net, at 5x generation cost.** Modest, not dramatic -- only helps when the model's errors
are inconsistent across samples; a systematic wrong belief just gets confirmed by majority vote,
not corrected.

## 5. Reliability & Efficiency

- **Guardrails**: SQLGlot SELECT-only gate + read-only DB connection + row cap + timeout. All 7
  adversarial/legitimate tests passed. One real gap found and disclosed: a multi-statement
  injection (`SELECT ...; DROP TABLE ...;`) was not caught by SQLGlot itself -- only by the
  read-only connection refusing the DROP. A second injected SELECT would not have been caught by
  either layer. Documented as a known residual limitation, not silently fixed.
- **Quantization (Q4 vs Q8)**: identical accuracy (55.0% both, n=20 subset), Q4 ~36% faster.
  Validates the VRAM-driven Q4 default from Phase 0 cost nothing in accuracy. fp16 excluded
  (would leave almost no VRAM headroom on the 15.6GB T4).

## 6. Final System

`repair loop -> (on exhaustion) self-consistency fallback -> guardrail gate`

| System | Accuracy |
|---|---|
| Baseline | 56/100 = 56.0% |
| Repair loop only | 59/100 = 59.0% |
| Final system | 58/100 = 58.0% |

The final-system number is roughly flat against repair-loop-only, and that gap is smaller than
run-to-run sampling noise already observed elsewhere in this project (the same Q4 subset swung
from 45% to 55% between two identical runs) -- reported honestly as inconclusive rather than
claimed as an improvement. What's reliable: both scaffolded systems sit meaningfully above the
single-shot baseline. This run was not instrumented to record which path (repair-loop success vs.
fallback) each prediction took -- a real gap for a complete cost analysis, disclosed rather than
hidden.

## 7. What Was Deliberately Not Done, and Why

| Excluded | Reason |
|---|---|
| Retrieval / schema-linking | Schema is 12 tables -- too small to justify it. |
| Multi-agent design | One agent, one responsibility covers this workflow. |
| LangGraph HITL / checkpointer / complex branching | No reviewer step; harness logging already handles resumability; one decision point is the whole control flow. |
| Full BIRD-dev run | Mini-Dev is an official representative subset; 3x the compute for no new evidence. |
| CSC-SQL corrective-merge step | Plain majority voting captures most of the benefit without a second LLM call to justify. |
| Full ReFoRCE / SLM-SQL replication | Solves problems (huge enterprise schemas, training infra) this project doesn't have. |
| vLLM on T4 | Turing lacks bf16/FlashAttention-2; quantization comparison already answers the efficiency question without the instability risk. |
| Unqualified scalability claims | No load-test evidence beyond what's measured here. |
| FastAPI as a required deliverable | CLI (`code/query.py`) demos the same thing without Colab networking friction. |

## 8. Infrastructure Reality (worth knowing, not hiding)

Ollama on this Colab T4 setup crashed recurringly under sustained generation load throughout this
project -- the server process would die (GPU memory evicted, port stops responding) while a stale
process entry remained, roughly every 10-80 queries depending on the model. Root cause not fully
diagnosed. Mitigated with: a `func_timeout` hard backstop per request (since `requests`' own
timeout didn't reliably fire when the server died mid-request), automatic health-check-and-restart
between small chunks, and append-as-you-go/resume-skip logging throughout the harness so no
progress was ever lost to a crash. This consumed more real time than any other part of the project
and is itself a legitimate finding about the limits of this specific inference stack, not a detour.

## 9. Interview Cheat Sheet

- Baseline: 56% custom / 43.6% BIRD (Qwen); 37% custom / 1.8% BIRD (SQLCoder, with disclosed anomaly)
- Repair loop: +3 net (8 fixed / 5 regressed)
- Self-consistency: +1 on subset, at 5x cost
- Final system: 58%, statistically indistinguishable from repair-loop-only given observed noise
- Guardrails: 7/7 tests passed, one real multi-statement gap disclosed
- Quantization: Q4 == Q8 accuracy, Q4 36% faster
- Why LangGraph: deliberate learning choice, not necessity -- a while-loop would score identically
- Why each "excluded" item was skipped (table above)
- The infrastructure section above, unprompted, as evidence of real engineering judgment under
  a genuinely unstable environment
