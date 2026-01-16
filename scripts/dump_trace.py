"""Dump SAGA trace.db content for analysis."""
import sqlite3
import json
import sys

def dump_trace(run_id: str):
    db_path = f"runs/{run_id}/trace.db"
    db = sqlite3.connect(db_path)
    cur = db.cursor()

    print("=" * 60)
    print("SAGA TRACE ANALYSIS")
    print(f"Run ID: {run_id}")
    print("=" * 60)
    
    print("\n# NODES (Agent Execution Stages)")
    print("-" * 40)
    for row in cur.execute("SELECT node_name, input_summary, output_summary, goal_set_version, elapsed_ms FROM nodes"):
        node_name, inp, out, ver, elapsed = row
        print(f"\n## {node_name} (elapsed: {elapsed}ms)")
        print(f"  Input: {inp}")
        print(f"  Output: {out}")
        print(f"  Goal Version: {ver}")
    
    print("\n" + "=" * 60)
    print("# CANDIDATES (Optimization Results)")
    print("-" * 40)
    for row in cur.execute("SELECT candidate_id, text, score_vector, objective_weights FROM candidates"):
        cid, text, scores, weights = row
        print(f"\n## {cid}")
        print(f"  Text: {text}")
        print(f"  Scores: {scores}")
        print(f"  Weights: {weights}")
    
    db.close()

if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "38624388b2ff497bb0d5926199afdc19"
    dump_trace(run_id)
