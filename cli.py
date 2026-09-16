"""
cli.py — Unified Production CLI for SDHD Hallucination Detection (Phase 10)
===========================================================================
Provides a clean, unified command-line entry point for:
1. Single Code Snippet / Single File Analysis
2. Project-Wide Multi-File Repository Analysis
3. Automated Benchmark Reproductions (RQ1, RQ2, RQ3, All)
"""

import argparse
import json
import os
import sys
from typing import Optional

from sdhd_pipeline import SDHD_Pipeline
from cross_file_analyzer import MultiFileSDHDRunner, CrossFileStaticDetector, ProjectSymbolTable
from evaluate_rq1 import run_rq1_pipeline
from ablation import run_rq2_pipeline
from evaluate_rq3 import run_rq3_pipeline


def parse_args():
    parser = argparse.ArgumentParser(
        prog="sdhd",
        description="SDHD: Static-Dynamic Hallucination Detection Framework for LLM-Generated Python Code"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--code",
        type=str,
        help="Inline Python source code string to evaluate."
    )
    group.add_argument(
        "--file",
        type=str,
        help="Path to a single Python (.py) file to evaluate."
    )
    group.add_argument(
        "--project-dir",
        type=str,
        help="Path to a project directory for multi-file / cross-module analysis."
    )
    group.add_argument(
        "--benchmark",
        choices=["rq1", "rq2", "rq3", "all"],
        help="Run paper benchmark reproduction suite (RQ1, RQ2, RQ3, or all)."
    )

    # Configuration options
    parser.add_argument(
        "--prompt",
        type=str,
        default="Verify code functionality and correct execution.",
        help="Natural language prompt / requirement specification."
    )
    parser.add_argument(
        "--c-min",
        type=int,
        default=10,
        help="Minimum dynamic test coverage threshold (default: 10)."
    )
    parser.add_argument(
        "--i-max",
        type=int,
        default=3,
        help="Maximum refinement iterations (default: 3)."
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Subprocess sandbox execution timeout in seconds (default: 5)."
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Path to save JSON analysis report."
    )
    parser.add_argument(
        "--output-md",
        type=str,
        default=None,
        help="Path to save Markdown analysis report."
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Run static analysis only (skip dynamic test execution)."
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # 1. Benchmark Execution Mode
    if args.benchmark:
        print(f"\n[SDHD CLI] Starting Benchmark Suite: {args.benchmark.upper()}")
        out_dir = "results"
        os.makedirs(out_dir, exist_ok=True)

        if args.benchmark in ("rq1", "all"):
            print("\n--- Running RQ1 Benchmark (Table III) ---")
            rep1, md1 = run_rq1_pipeline(output_dir=out_dir)
            print(md1)

        if args.benchmark in ("rq2", "all"):
            print("\n--- Running RQ2 Ablation Study (Table IV) ---")
            rep2, md2 = run_rq2_pipeline(output_dir=out_dir)
            print(md2)

        if args.benchmark in ("rq3", "all"):
            print("\n--- Running RQ3 Refinement & Efficiency (Tables V & VI, Figures 4 & 5) ---")
            rep3 = run_rq3_pipeline(output_dir=out_dir)

        print(f"\n[SDHD CLI] Benchmark complete! Results saved in '{out_dir}/'.")
        return 0

    # 2. Project Directory Mode
    if args.project_dir:
        if not os.path.exists(args.project_dir):
            print(f"Error: Project directory '{args.project_dir}' not found.", file=sys.stderr)
            return 1

        print(f"\n[SDHD CLI] Analyzing multi-file project: '{args.project_dir}'...")
        runner = MultiFileSDHDRunner(
            project_dir=args.project_dir,
            timeout=args.timeout,
            c_min=args.c_min,
            i_max=args.i_max
        )
        report = runner.analyze_project()
        md_content = runner.generate_project_markdown(report)

        print("\n" + md_content)

        if args.output_json:
            with open(args.output_json, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"[SDHD CLI] JSON report written to: {args.output_json}")

        if args.output_md:
            with open(args.output_md, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"[SDHD CLI] Markdown report written to: {args.output_md}")

        return 0 if report.get("overall_status") == "PASS" else 2

    # 3. Single Code Snippet or File Mode
    source_code = ""
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: Source file '{args.file}' not found.", file=sys.stderr)
            return 1
        with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
            source_code = f.read()
    else:
        source_code = args.code

    print("\n[SDHD CLI] Analyzing code snippet...")
    pipeline = SDHD_Pipeline(
        timeout=args.timeout,
        c_min=args.c_min,
        i_max=args.i_max
    )

    def _default_gen(r, c, f, cnt):
        return []

    report = pipeline.run(
        user_prompt=args.prompt,
        generated_code=source_code,
        test_gen_fn=_default_gen if args.static_only else None
    )

    status = report["summary"]["overall_status"]
    total = report["summary"]["total_hallucinations"]
    print(f"\n[SDHD Result] Status: {status} | Total Hallucinations: {total}")
    print(f"Breakdown: {report['summary']['breakdown_by_type']}")

    if total > 0:
        print("\nIdentified Hallucinations:")
        for h in report["hallucinations"]:
            print(f" - [{h.get('type_code')}] '{h.get('variable_name')}' at line {h.get('line_number')}: {h.get('detail')}")

    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[SDHD CLI] JSON report written to: {args.output_json}")

    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
