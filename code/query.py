"""
CLI entrypoint for the Agentic Text-to-SQL system.
Usage: python query.py "How many customers are there in total?"
"""
import sys, json
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
import requests, duckdb
from func_timeout import func_timeout, FunctionTimedOut

sys.path.insert(0, "/content/text2sql-project/code")
import harness

MODEL = "qwen2.5-coder:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"
DB_PATH = "/content/text2sql-project/data/food_delivery.duckdb"
MAX_ATTEMPTS = 3
MAX_ROWS = 1000


def get_duckdb_schema_text(db_path):
    con = duckdb.connect(db_path, read_only=True)
    tables = con.execute("SHOW TABLES").fetchall()
    schema_lines = []
    for (table_name,) in tables:
        cols = con.execute(f"DESCRIBE {table_name}").fetchall()
        col_defs = ", ".join(f"{c[0]} {c[1]}" for c in cols)
        schema_lines.append(f"CREATE TABLE {table_name} ({col_defs});")
    con.close()
    return "\n".join(schema_lines)


custom_schema_text = get_duckdb_schema_text(DB_PATH)


def clean_response(raw):
    raw = raw.strip().strip("`")
    if raw.lower().startswith("sql"):
        raw = raw[3:].strip()
    return raw


class RepairState(TypedDict):
    question: str
    sql: str
    attempt: int
    last_error: Optional[str]
    status: str


def generate_node(state):
    error_context = ""
    if state.get("last_error"):
        error_context = f"\n\nYour previous attempt was:\n{state['sql']}\nIt failed with this error:\n{state['last_error']}\nPlease fix the query."
    prompt = f"""You are a SQL expert. Given the database schema below, write a single SQL SELECT query that answers the question.
Only output the SQL query, with no explanation, no markdown formatting, no code fences.

Schema:
{custom_schema_text}

Question: {state['question']}{error_context}

SQL:"""
    try:
        resp = requests.post(OLLAMA_URL, json={"model": MODEL, "prompt": prompt, "stream": False}, timeout=90)
        resp.raise_for_status()
        sql = clean_response(resp.json()["response"])
    except Exception as e:
        sql = f"-- GENERATION_FAILED: {e}"
    return {**state, "sql": sql, "attempt": state["attempt"] + 1}


def validate_node(state):
    is_valid, err, tables, tier = harness.validate_and_classify(state["sql"])
    if not is_valid:
        return {**state, "status": "pending", "last_error": f"validation error: {err}"}
    return {**state, "status": "validated"}


def execute_node(state):
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        con.execute(state["sql"]).fetchall()
        return {**state, "status": "success"}
    except Exception as e:
        return {**state, "status": "pending", "last_error": f"execution error: {e}"}
    finally:
        con.close()


def route(state):
    if state["status"] == "success":
        return "end"
    if state["attempt"] >= MAX_ATTEMPTS:
        return "end"
    return "retry"


def after_validate(state):
    return "execute" if state["status"] == "validated" else route(state)


graph = StateGraph(RepairState)
graph.add_node("generate", generate_node)
graph.add_node("validate", validate_node)
graph.add_node("execute", execute_node)
graph.set_entry_point("generate")
graph.add_edge("generate", "validate")
graph.add_conditional_edges("validate", after_validate, {"execute": "execute", "retry": "generate", "end": END})
graph.add_conditional_edges("execute", route, {"retry": "generate", "end": END})
compiled_graph = graph.compile()


def generate_once(question):
    prompt = f"""You are a SQL expert. Given the database schema below, write a single SQL SELECT query that answers the question.
Only output the SQL query, with no explanation, no markdown formatting, no code fences.

Schema:
{custom_schema_text}

Question: {question}

SQL:"""
    try:
        resp = requests.post(OLLAMA_URL, json={"model": MODEL, "prompt": prompt, "stream": False}, timeout=90)
        resp.raise_for_status()
        return clean_response(resp.json()["response"])
    except Exception as e:
        return f"-- GENERATION_FAILED: {e}"


def predict_self_consistency(question, n=5):
    candidates = [generate_once(question) for _ in range(n)]

    def run(sql):
        con = duckdb.connect(DB_PATH, read_only=True)
        try:
            return tuple(sorted(con.execute(sql).fetchall()))
        except Exception:
            return None
        finally:
            con.close()

    result_groups = {}
    for sql in candidates:
        r = run(sql)
        if r is not None:
            result_groups.setdefault(r, []).append(sql)
    if not result_groups:
        return candidates[0]
    return max(result_groups.values(), key=len)[0]


def execute_with_guardrails(sql, db_path=DB_PATH, max_rows=MAX_ROWS, timeout=30):
    is_valid, err, tables, tier = harness.validate_and_classify(sql)
    if not is_valid:
        return {"allowed": False, "reason": err}

    def run():
        con = duckdb.connect(db_path, read_only=True)
        try:
            return con.execute(sql).fetchmany(max_rows + 1)
        finally:
            con.close()

    try:
        rows = func_timeout(timeout, run)
        return {"allowed": True, "reason": None, "rows": rows}
    except FunctionTimedOut:
        return {"allowed": False, "reason": f"exceeded {timeout}s timeout"}
    except Exception as e:
        return {"allowed": False, "reason": f"execution error: {e}"}


def answer_question(question):
    result = compiled_graph.invoke({"question": question, "sql": "", "attempt": 0, "last_error": None, "status": "pending"})
    sql = result["sql"] if result["status"] == "success" else predict_self_consistency(question, n=5)
    guard = execute_with_guardrails(sql)
    if not guard["allowed"]:
        return sql, None, guard["reason"]
    return sql, guard["rows"], None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python query.py \"your question here\"")
        sys.exit(1)
    question = sys.argv[1]
    sql, rows, error = answer_question(question)
    print(f"Question: {question}")
    print(f"SQL: {sql}")
    if error:
        print(f"Blocked/failed: {error}")
    else:
        print(f"Result ({len(rows)} rows):")
        for row in rows[:20]:
            print(f"  {row}")
