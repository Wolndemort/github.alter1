#!/usr/bin/env python3
"""Score saved model responses without making any provider calls.

Input JSON format:
[{"model":"alter", "case_id":"small_hello", "response":"...", "latency_ms":120}]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from utils.benchmark import aggregate_model_reports, score_records
from utils.eval_suite import load_russian_suite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = json.loads(args.input.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in load_russian_suite()}
    scored = score_records(cases, records)
    report = {"reports": aggregate_model_reports(scored), "records": scored}
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
