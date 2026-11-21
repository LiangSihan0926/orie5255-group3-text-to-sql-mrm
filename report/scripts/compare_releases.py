"""Compare versioned, published gold SQL on one pinned, read-only BIRD snapshot."""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from recount_financial_labels import read_labels

DB_SHA = "d15d89cdb068a202b6f2b99342af44dffc1d52545b39ceaf62efdc0ba570101e"


CASE_FILE_SHA = {
    "financial.json": "3176ef1234a10189373c37393c09d1884ca4e9074e77cd877c85dff638b30de9",
    "financial_corrected_sql.json": "1ccda083a25cbec02371c3f2ce866e17f7d8fbc7318b519e13b6ebdd4fdec96f",
    "financial_corrected.json": "cd9f8c1faafe3c50fdc2388e90dc2b8fa647d480a231cd6935192c3baa3e9ee6",
    "bird_financial_dev.json": "edce65591214820b0c858c9f0d7b453eb5d405a3a7c65d37156fafb5cd09d15c",
}


def load_cases(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != CASE_FILE_SHA[path.name]:
        raise ValueError(f"Unexpected release file: {path}")
    rows = json.loads(path.read_text(encoding="utf-8"))
    by_id = {r["question_id"]: r for r in rows}
    if len(rows) != 106 or len(by_id) != 106:
        raise ValueError(f"Expected 106 distinct financial items in {path}")
    return by_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("authors", type=Path, help="Pinned paper-author repository root")
    parser.add_argument("team", type=Path, help="Pinned capstone repository root")
    parser.add_argument("output", type=Path)
    parser.add_argument("--db", type=Path, help="An uncompressed copy of the pinned SQLite snapshot")
    args = parser.parse_args()
    author_data = args.authors / "datasets"
    sources = {"original": author_data / "financial.json",
               "sql_only": author_data / "financial_corrected_sql.json",
               "both": author_data / "financial_corrected.json",
               "team": args.team / "archive/text2sql_bird/bird_financial_dev.json"}
    cases = {name: load_cases(path) for name, path in sources.items()}
    base = cases["original"]
    if any(ds.keys() != base.keys() for ds in cases.values()):
        raise ValueError("Release IDs disagree")
    labels = read_labels(args.authors / "annotations/financial_annotations.csv", set(base))
    db = args.db or author_data / "financial.sqlite"
    if hashlib.sha256(db.read_bytes()).hexdigest() != DB_SHA:
        raise ValueError("Unexpected financial snapshot")
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    con.execute("PRAGMA query_only=ON")
    results = []
    try:
        for case_id in sorted(base):
            cache = {}
            for variant, ds in cases.items():
                query = ds[case_id]["SQL"]
                if query not in cache:
                    # The authors compare complete rows as a multiset, including duplicates.
                    cache[query] = Counter(con.execute(query))
                if variant == "original":
                    continue
                comparisons = ["original", "sql_only"] if variant == "both" else ["original"]
                for ref in comparisons:
                    ref_row = cases[ref][case_id]
                    results.append({
                        "id": case_id, "base": ref, "variant": variant,
                        "question_text_changed": ds[case_id]["question"] != ref_row["question"],
                        "sql_text_changed": query != ref_row["SQL"],
                        "result_multiset_changed": cache[query] != cache[ref_row["SQL"]],
                        "original_sql_error_label": 3 in labels[case_id],
                        "original_question_label": bool(labels[case_id] - {3}),
                    })
    finally:
        con.close()
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    for ref, name in sorted({(r["base"], r["variant"]) for r in results}):
        rows = [r for r in results if r["base"] == ref and r["variant"] == name]
        print(ref, name, {key: sum(r[key] for r in rows) for key in ("question_text_changed", "sql_text_changed", "result_multiset_changed")})
    sql_only = [r for r in results if r["variant"] == "sql_only" and r["result_multiset_changed"]]
    categories = Counter((r["original_sql_error_label"], r["original_question_label"]) for r in sql_only)
    print("Changed SQL-only outputs:", sum(count for (sql, _), count in categories.items() if sql),
          "with an SQL-error label,", categories[False, True], "with question labels only.")
    print("SQLite", sqlite3.sqlite_version)


if __name__ == "__main__":
    main()
