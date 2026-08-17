

## Improvement 3a — Reliability guardrails

All 7 adversarial/legitimate test cases behaved as expected (destructive DDL/DML blocked,
legitimate queries allowed). One finding worth flagging rather than hiding: the multi-statement
injection test (`SELECT ...; DROP TABLE ...;`) was **not** caught by the SQLGlot validation layer
itself -- it parsed through and was only stopped by DuckDB's read-only connection refusing the
DROP. This is a real, if narrow, gap: a second injected `SELECT` statement (not destructive) would
not have been caught by either layer. Documented as a known residual limitation rather than fixed
in this pass, given project time constraints -- the two layers cover different failure modes
(SQLGlot: statement type; read-only connection: destructive operations) and together block every
tested attack, but neither alone is sufficient.
