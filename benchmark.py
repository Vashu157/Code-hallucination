"""
benchmark.py – SDHD Pipeline Benchmark across MBPP, CodeHaluEval, and HalluCode
================================================================================
Supports multi-dataset evaluation across all three benchmarks (Section IV-A, Table II):
  1. MBPP (Clean-code pool for false-positive rate evaluation + synthetic mutations)
  2. CodeHaluEval (Dynamic execution benchmark with ground-truth labels and test suites)
  3. HalluCode (Static hallucination benchmark with 6-type annotations)
"""

import ast
import json
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from dataset_loaders import (
    DatasetRecord,
    load_mbpp,
    load_codehalueval,
    load_hallucode,
    load_all_datasets,
    get_dataset_summary
)
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
    """Loads `n` records from MBPP dataset with local fallback."""
    print(f"[Benchmark] Loading {n} records from MBPP dataset...")
    records_obj = load_mbpp(n=n, clean_only=True)
    records = [{"task_id": r.task_id, "text": r.prompt, "code": r.code} for r in records_obj]
    print(f"[Benchmark] Loaded {len(records)} records.")
    return records


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark Runners
# ─────────────────────────────────────────────────────────────────────────────

def run_benchmark(n_records: int = 20, inter_record_delay: float = 0.0) -> Dict[str, Any]:
    """
    Synthetic mutation benchmark loop on MBPP.
    """
    records = load_mbpp_records(n_records)
    pipeline = SDHD_Pipeline(timeout=5, max_retries=3, retry_delay=1.0)

    run_results: List[Dict[str, Any]] = []
    caught = 0
    missed = 0
    pipeline_errors = 0

    for idx, record in enumerate(records):
        prompt: str = record.get("text", "")
        original_code: str = record.get("code", "")
        task_id: int = record.get("task_id", idx)

        # Inject a synthetic bug
        mutated_code, strategy = inject_bug(original_code)

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

        if inter_record_delay > 0 and idx < len(records) - 1:
            time.sleep(inter_record_delay)

    mutation_catch_rates: Dict[str, Dict[str, int]] = {}
    for r in run_results:
        s = r.get("mutation_strategy", "unknown")
        mutation_catch_rates.setdefault(s, {"caught": 0, "missed": 0})
        if r.get("bug_caught"):
            mutation_catch_rates[s]["caught"] += 1
        else:
            mutation_catch_rates[s]["missed"] += 1

    final_report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "records_tested": len(records),
        "bugs_injected": len(records),
        "bugs_caught": caught,
        "bugs_missed": missed,
        "pipeline_errors": pipeline_errors,
        "catch_rate_pct": round(caught / len(records) * 100, 1) if records else 0,
        "catch_rate_by_mutation": mutation_catch_rates,
        "per_record_results": run_results,
    }

    return final_report


def run_multi_dataset_benchmark(
    datasets_dict: Optional[Dict[str, List[DatasetRecord]]] = None
) -> Dict[str, Any]:
    """
    Evaluates the SDHD pipeline across all three benchmarks (MBPP, CodeHaluEval, HalluCode)
    using ground-truth labeled instances (Section IV-A, Table II).
    """
    datasets = datasets_dict or load_all_datasets()
    pipeline = SDHD_Pipeline(timeout=5, c_min=10, i_max=3)

    results: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_summary": get_dataset_summary(datasets),
        "evaluation_by_dataset": {},
    }

    for dname, recs in datasets.items():
        total_eval = len(recs)
        correct_predictions = 0
        per_record = []

        for rec in recs:
            try:
                # Provide custom test runner if tests available
                mock_gen = None
                if rec.tests:
                    def _gen_fn(r_spec, code_str, feedback_str, count):
                        return rec.tests[:count] if len(rec.tests) >= count else rec.tests * (count // len(rec.tests) + 1)
                    mock_gen = _gen_fn

                report = pipeline.run(user_prompt=rec.prompt, generated_code=rec.code, test_gen_fn=mock_gen)
                pred_hallucinated = report["summary"]["total_hallucinations"] > 0
                is_correct = (pred_hallucinated == rec.is_hallucinated)

                if is_correct:
                    correct_predictions += 1

                per_record.append({
                    "task_id": rec.task_id,
                    "ground_truth_hallucinated": rec.is_hallucinated,
                    "predicted_hallucinated": pred_hallucinated,
                    "total_hallucinations_detected": report["summary"]["total_hallucinations"],
                    "breakdown": report["summary"]["breakdown_by_type"],
                    "correct": is_correct
                })
            except Exception as e:
                per_record.append({
                    "task_id": rec.task_id,
                    "error": str(e),
                    "correct": False
                })

        accuracy = round(correct_predictions / total_eval * 100, 1) if total_eval else 0.0
        results["evaluation_by_dataset"][dname] = {
            "total_tasks": total_eval,
            "correct_predictions": correct_predictions,
            "accuracy_pct": accuracy,
            "records": per_record
        }

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Running Multi-Dataset Benchmark (Table II Benchmarks) ===")
    multi_report = run_multi_dataset_benchmark()

    for dname, res in multi_report["evaluation_by_dataset"].items():
        print(f"[{dname}] Evaluated: {res['total_tasks']} | Correct: {res['correct_predictions']} | Accuracy: {res['accuracy_pct']}%")

    with open("benchmark_report.json", "w") as f:
        json.dump(multi_report, f, indent=2)
    print("\n[Benchmark] Report saved to benchmark_report.json")

