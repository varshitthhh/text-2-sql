# Failure Analysis — Qwen2.5-Coder-7B-Instruct (custom food-delivery benchmark)

Baseline: 56/100 correct.

## By failure category (overall)

| Category | Count |
|---|---|
| correct | 56 |
| silently_wrong | 37 |
| execution_error | 7 |
| parse_error | 0 |

## Cross-tabulation: tier x failure category

| Tier | correct | silently_wrong | execution_error | parse_error |
|---|---|---|---|---|
| single_table | 20 | 0 | 0 | 0 |
| join | 17 | 3 | 0 | 0 |
| aggregation | 13 | 5 | 2 | 0 |
| nested_subquery | 6 | 13 | 1 | 0 |
| ambiguous | 0 | 16 | 4 | 0 |

**Key implication:** the repair loop (Phase 5) can only ever catch `parse_error` and `execution_error` (7 cases combined) — it structurally cannot fix `silently_wrong` results (37 cases), since nothing fails at execution time. That gap is the direct justification for self-consistency (Phase 6).