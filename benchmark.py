"""
benchmark.py – SDHD Pipeline Benchmark using the MBPP Dataset
==============================================================
Loads the first 20 records from the HuggingFace MBPP dataset, injects
synthetic bugs into the code, runs the SDHD_Pipeline, and outputs a
structured summary report of caught vs. missed hallucinations.
"""

import ast
import json
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from datasets import load_dataset

from sdhd_pipeline import SDHD_Pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Mutation Strategies
# ─────────────────────────────────────────────────────────────────────────────

class _VariableRenamer(ast.NodeTransformer):
    """Renames the first user-defined variable it finds to a nonsense name."""
    def __init__(self) -> None:
        self._renamed: Optional[str] = None

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        if self._renamed is None:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id not in ("self",):
                    self._renamed = target.id
                    target.id = "__hallucinated_var__"
                    break
        return self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if self._renamed and node.id == self._renamed and isinstance(node.ctx, ast.Load):
            node.id = "__hallucinated_var__"
        return node


class _LoopBoundaryShifter(ast.NodeTransformer):
    """Shifts the upper bound of the first range() call by an offset of +99."""
    _done = False

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if (not self._done
                and isinstance(node.func, ast.Name)
                and node.func.id == "range"
                and node.args):
            last_arg = node.args[-1]
            if isinstance(last_arg, ast.Constant) and isinstance(last_arg.value, int):
                node.args[-1] = ast.Constant(value=last_arg.value + 99)
                self._done = True
        return self.generic_visit(node)


class _ReturnValueCorruptor(ast.NodeTransformer):
    """Replaces the first literal return value with -9999."""
    _done = False

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if not self._done and node.value is not None:
            if isinstance(node.value, ast.Constant):
                node.value = ast.Constant(value=-9999)
                self._done = True
            elif isinstance(node.value, ast.Name):
                node.value = ast.Constant(value=-9999)
                self._done = True
        return self.generic_visit(node)


class _UndefinedCallInjector(ast.NodeTransformer):
    """Inserts a call to an undefined function `phantom_lib.compute()` at the top of the first function body."""
    _done = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if not self._done and node.body:
            phantom_call = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="phantom_lib", ctx=ast.Load()),
                        attr="compute",
                        ctx=ast.Load()
                    ),
                    args=[],
                    keywords=[]
                )
            )
            node.body.insert(0, phantom_call)
            self._done = True
        return self.generic_visit(node)


# Map of mutation names to their transformer class
MUTATIONS: Dict[str, type] = {
    "variable_rename":    _VariableRenamer,
    "loop_boundary_shift": _LoopBoundaryShifter,
    "return_value_corrupt": _ReturnValueCorruptor,
    "undefined_call":     _UndefinedCallInjector,
}


def inject_bug(source_code: str, strategy: Optional[str] = None) -> Tuple[str, str]:
    """
    Applies a random (or specified) AST mutation to the source code.

    Returns:
        (mutated_code, strategy_name) – the modified code string and the strategy used.
    """
    strategy = strategy or random.choice(list(MUTATIONS.keys()))
    try:
        tree = ast.parse(source_code)
        transformer = MUTATIONS[strategy]()
        mutated_tree = transformer.visit(tree)
        ast.fix_missing_locations(mutated_tree)
        return ast.unparse(mutated_tree), strategy
    except Exception:
        # If mutation fails (e.g. syntax edge-case), return original + label
        return source_code, strategy


# ─────────────────────────────────────────────────────────────────────────────
# Dataset Loading
# ─────────────────────────────────────────────────────────────────────────────

def load_mbpp_records(n: int = 20) -> List[Dict[str, Any]]:
    """Loads the first `n` records from the MBPP test split."""
    print(f"[Benchmark] Loading {n} records from MBPP dataset...")
    ds = load_dataset("mbpp", split="test")
    records = [ds[i] for i in range(min(n, len(ds)))]
    print(f"[Benchmark] Loaded {len(records)} records.")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_benchmark(n_records: int = 20, inter_record_delay: float = 13.0) -> Dict[str, Any]:
    """
    Main benchmark loop.
    For each MBPP record:
      1. Inject a synthetic bug.
      2. Run the SDHD_Pipeline on the mutated code.
      3. Record whether any hallucination was caught.

    Args:
        n_records:           Number of MBPP records to evaluate.
        inter_record_delay:  Seconds to sleep between records to respect the
                             free-tier Gemini quota (5 req/min = 12 s/req).
                             Default 13 s adds a small safety buffer.

    Returns a structured summary report.
    """
    records = load_mbpp_records(n_records)
    # retry_delay=13 s keeps individual retries within quota as well
    pipeline = SDHD_Pipeline(timeout=5, max_retries=3, retry_delay=13.0)

    run_results: List[Dict[str, Any]] = []
    caught = 0
    missed = 0
    pipeline_errors = 0

    for idx, record in enumerate(records):
        prompt: str = record.get("text", "")
        original_code: str = record.get("code", "")
        task_id: int = record.get("task_id", idx)

        print(f"\n{'='*60}")
        print(f"[Benchmark] Record {idx + 1}/{n_records} | task_id={task_id}")

        # Inject a synthetic bug
        mutated_code, strategy = inject_bug(original_code)
        print(f"[Benchmark] Injected mutation: '{strategy}'")

        # Run the pipeline (skip dynamic for speed; just static is reliable here)
        try:
            report = pipeline.run(user_prompt=prompt, generated_code=mutated_code)
        except Exception as e:
            pipeline_errors += 1
            run_results.append({
                "task_id": task_id,
                "mutation_strategy": strategy,
                "pipeline_error": str(e),
                "bug_caught": False,
            })
            print(f"[Benchmark] Pipeline error: {e}")
            continue

        total_found = report["summary"].get("total_hallucinations", 0)
        was_caught = total_found > 0

        if was_caught:
            caught += 1
        else:
            missed += 1

        run_results.append({
            "task_id": task_id,
            "mutation_strategy": strategy,
            "hallucinations_found": total_found,
            "breakdown": report["summary"].get("breakdown_by_type", {}),
            "bug_caught": was_caught,
            "pipeline_errors_this_run": len(report.get("errors", [])),
        })

        print(f"[Benchmark] Hallucinations found: {total_found} | Caught: {was_caught}")

        # Rate-limit pacing: sleep between records (skip after the last one)
        if idx < len(records) - 1:
            print(f"[Benchmark] Pausing {inter_record_delay:.0f}s to respect API quota...")
            time.sleep(inter_record_delay)

    # ── Build final summary ──────────────────────────────────────────
    mutation_catch_rates: Dict[str, Dict[str, int]] = {}
    for r in run_results:
        s = r.get("mutation_strategy", "unknown")
        mutation_catch_rates.setdefault(s, {"caught": 0, "missed": 0})
        if r.get("bug_caught"):
            mutation_catch_rates[s]["caught"] += 1
        else:
            mutation_catch_rates[s]["missed"] += 1

    final_report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "records_tested": n_records,
        "bugs_injected": n_records,
        "bugs_caught": caught,
        "bugs_missed": missed,
        "pipeline_errors": pipeline_errors,
        "catch_rate_pct": round(caught / n_records * 100, 1) if n_records else 0,
        "catch_rate_by_mutation": mutation_catch_rates,
        "per_record_results": run_results,
    }

    return final_report


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    report = run_benchmark(n_records=20)

    print("\n" + "=" * 60)
    print("         SDHD BENCHMARK SUMMARY REPORT")
    print("=" * 60)
    print(f"  Records tested   : {report['records_tested']}")
    print(f"  Bugs injected    : {report['bugs_injected']}")
    print(f"  Bugs caught      : {report['bugs_caught']}")
    print(f"  Bugs missed      : {report['bugs_missed']}")
    print(f"  Pipeline errors  : {report['pipeline_errors']}")
    print(f"  Catch rate       : {report['catch_rate_pct']}%")
    print("\n  Catch rate by mutation strategy:")
    for strategy, counts in report["catch_rate_by_mutation"].items():
        total = counts["caught"] + counts["missed"]
        rate = round(counts["caught"] / total * 100, 1) if total else 0
        print(f"    {strategy:<28}: {counts['caught']}/{total} ({rate}%)")
    print("=" * 60)

    # Save full JSON report to disk
    report_path = "benchmark_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[Benchmark] Full report saved to: {report_path}")
