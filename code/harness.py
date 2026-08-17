
# Reusable evaluation harness for the Text-to-SQL project.
# Two evaluation paths:
#   - custom domain benchmark (DuckDB): per-query predict + execute + compare, logged incrementally.
#   - BIRD Mini-Dev (SQLite): per-query predictions logged incrementally, scored in one batch pass
#     via BIRD's own official evaluation_ex.py (their tooling is batch-oriented; no reason to fight that).
import duckdb
import sqlglot
from sqlglot import exp
from func_timeout import func_timeout, FunctionTimedOut
import json
import os
import subprocess


def validate_and_classify(sql: str):
    """Returns (is_valid, error_message, tables, complexity_tier) for a SQL string."""
    try:
        parsed = sqlglot.parse_one(sql, read="duckdb")
    except Exception as e:
        return False, f"Parse error: {e}", [], None

    if not isinstance(parsed, exp.Select):
        return False, "Only SELECT statements are allowed.", [], None

    tables = sorted({t.name for t in parsed.find_all(exp.Table)})
    join_count = len(list(parsed.find_all(exp.Join)))
    has_subquery = len(list(parsed.find_all(exp.Subquery))) > 0
    has_group_by = parsed.find(exp.Group) is not None

    if has_subquery:
        tier = "nested_subquery"
    elif has_group_by:
        tier = "aggregation"
    elif join_count >= 1:
        tier = "join"
    else:
        tier = "single_table"

    return True, None, tables, tier


def _run_query_duckdb(sql, db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def execute_and_compare(predicted_sql, gold_sql, db_path, float_decimals=2, timeout=30.0):
    """Set-based comparison with float tolerance, for our custom DuckDB benchmark only."""
    try:
        pred_result = func_timeout(timeout, _run_query_duckdb, args=(predicted_sql, db_path))
    except FunctionTimedOut:
        return {"match": False, "error": "predicted SQL timed out", "predicted_rows": None, "gold_rows": None}
    except Exception as e:
        return {"match": False, "error": f"predicted SQL error: {e}", "predicted_rows": None, "gold_rows": None}

    gold_result = func_timeout(timeout, _run_query_duckdb, args=(gold_sql, db_path))

    def normalize(rows):
        return {tuple(round(v, float_decimals) if isinstance(v, float) else v for v in row) for row in rows}

    pred_set, gold_set = normalize(pred_result), normalize(gold_result)
    return {"match": pred_set == gold_set, "error": None,
            "predicted_rows": len(pred_result), "gold_rows": len(gold_result)}


def run_custom_eval(examples, predict_fn, db_path, results_path, system_name):
    """
    examples: list of {"id", "question", "sql", "tier", ...}
    predict_fn: callable(question) -> predicted_sql string
    Appends one JSON line per example to results_path. Skips ids already present on resume.
    """
    already_done = set()
    if os.path.exists(results_path):
        with open(results_path) as f:
            for line in f:
                if line.strip():
                    already_done.add(json.loads(line)["id"])

    with open(results_path, "a") as out:
        for ex in examples:
            if ex["id"] in already_done:
                continue

            predicted_sql = predict_fn(ex["question"])
            is_valid, val_err, tables, _ = validate_and_classify(predicted_sql)

            if not is_valid:
                record = {"id": ex["id"], "system": system_name, "question": ex["question"],
                          "tier": ex["tier"], "predicted_sql": predicted_sql,
                          "match": False, "error": f"guardrail rejected: {val_err}"}
            else:
                cmp_result = execute_and_compare(predicted_sql, ex["sql"], db_path)
                record = {"id": ex["id"], "system": system_name, "question": ex["question"],
                          "tier": ex["tier"], "predicted_sql": predicted_sql,
                          "match": cmp_result["match"], "error": cmp_result["error"]}
            out.write(json.dumps(record) + "\n")
            out.flush()


def run_bird_predictions(examples, predict_fn, predictions_path):
    """
    examples: list of BIRD records with 'db_id', 'question', 'evidence'
    predict_fn: callable(question, evidence, db_id) -> predicted_sql string
    Builds/updates the predictions JSON in BIRD's required format: {index: "SQL\\t----- bird -----\\tdb_id"}
    Resumable: loads existing predictions and only fills in missing indices.
    """
    predictions = {}
    if os.path.exists(predictions_path):
        with open(predictions_path) as f:
            predictions = json.load(f)

    for idx, ex in enumerate(examples):
        key = str(idx)
        if key in predictions:
            continue
        predicted_sql = predict_fn(ex["question"], ex.get("evidence", ""), ex["db_id"])
        predictions[key] = f"{predicted_sql}\t----- bird -----\t{ex['db_id']}"
        with open(predictions_path, "w") as f:
            json.dump(predictions, f, indent=2)

    return predictions


def score_bird_predictions(predictions_path, ground_truth_path, db_root_path, diff_json_path,
                            output_log_path, mini_dev_repo="/content/mini_dev_repo",
                            num_cpus=2, meta_time_out=30.0):
    """Invokes BIRD's official evaluation_ex.py as a batch scorer over the full predictions file."""
    result = subprocess.run(
        ["python3", "-u", f"{mini_dev_repo}/evaluation/evaluation_ex.py",
         "--predicted_sql_path", predictions_path, "--ground_truth_path", ground_truth_path,
         "--db_root_path", db_root_path, "--num_cpus", str(num_cpus),
         "--meta_time_out", str(meta_time_out), "--diff_json_path", diff_json_path,
         "--sql_dialect", "SQLite", "--output_log_path", output_log_path],
        capture_output=True, text=True,
    )
    return result
