"""Recompute the report's supplementary checks on the bundled offline inputs."""
import gzip
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


REPORT = Path(__file__).resolve().parent
REPO = REPORT.parent
AUTHORS = REPORT / "inputs" / "wretblad"
EVIDENCE = REPORT / "evidence"


def run(script, *arguments):
    subprocess.run(
        [sys.executable, "-B", REPORT / "scripts" / script, *arguments],
        cwd=REPORT,
        check=True,
    )


def main():
    print(f"Python {sys.version.split()[0]} / SQLite {sqlite3.sqlite_version}", flush=True)
    run("recount_financial_labels.py", AUTHORS, "--check", EVIDENCE / "financial_label_recount.json")
    run("verify_archive_diagnostics.py", "--repo", REPO, "--check", EVIDENCE / "archive_diagnostics.json")
    run("audit_pilot_disclosures.py", "--repo", REPO, "--check", EVIDENCE / "pilot_disclosure_audit.csv")
    run("verify_clarified_portfolio.py", "--check", REPO / "evidence" / "clarified_portfolio_queries.csv")
    run("audit_clarification_paths.py", "--check", EVIDENCE / "clarification_paths.csv")
    run("audit_withdrawal_timing.py", "--check", EVIDENCE / "withdrawal_timing.json")
    run("verify_t4_schema_stress.py", "--repo", REPO, "--check", EVIDENCE / "t4_schema_stress.json")
    run("check_snapshot_binding.py", "--check", EVIDENCE / "snapshot_binding.json")
    with TemporaryDirectory() as work:
        snapshot = Path(work) / "financial.sqlite"
        with gzip.open(REPO / "data" / "financial.sqlite.gz", "rb") as source, snapshot.open("wb") as target:
            shutil.copyfileobj(source, target)
        run("replay_published_example.py", "--db", snapshot, "--check", EVIDENCE / "published_q177_replay.json")
        comparison = Path(work) / "gold_release_comparison.csv"
        run("compare_releases.py", AUTHORS, REPO, comparison, "--db", snapshot)
        if comparison.read_bytes() != (EVIDENCE / comparison.name).read_bytes():
            raise SystemExit("The reference comparison differs from the archived CSV.")
    print("All supplementary checks agree with the archived evidence, including 424 release comparisons.")


if __name__ == "__main__":
    main()
