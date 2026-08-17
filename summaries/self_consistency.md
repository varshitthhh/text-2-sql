

## Improvement 2 — Self-consistency (majority vote, n=5) — custom benchmark subset

**Self-consistency accuracy: 11/20 = 55.0%** (baseline on same subset: 10/20 = 50.0%, net +1)
**Cost: 5x generation calls per query vs. single-shot baseline.**

Modest improvement, not dramatic -- consistent with the technique's role: it targets "silently
wrong" cases (executes cleanly, wrong result) that the repair loop structurally cannot touch, but
only helps when the model's errors are inconsistent across samples (voting works) rather than a
systematic, repeated misunderstanding (e.g., the `ratings` join-path confusion identified in
Phase 4/5 -- if the model makes the *same* wrong assumption in most of the 5 samples, majority vote
just confirms the wrong answer rather than correcting it). Evaluated on a stratified 20-example
subset (4 per tier) rather than the full 100, per the roadmap's explicit cost-budget scoping.
