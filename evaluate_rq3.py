"""
evaluate_rq3.py - RQ3 Refinement, Efficiency & Sensitivity Evaluation (Section IV-E)
====================================================================================
Reproduces RQ3 from the SDHD paper:
1. Table V: Impact of iterative feedback refinement over iterations (I=1, 2, 3).
2. Table VI: Runtime latency and computational efficiency breakdown (Static vs Dynamic vs Total).
3. Figures 4 & 5: Hyperparameter sensitivity sweeps across C_min in {5, 10, 15, 20} and I_max in {1, 2, 3, 4, 5}.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Callable

from baselines import calculate_metrics
from dataset_loaders import DatasetRecord, load_all_datasets
from sdhd_pipeline import SDHD_Pipeline
from static_analysis import detect_hallucinations


# =====================================================================
# 1. Table V: Iterative Refinement Tracker
# =====================================================================

class RQ3RefinementEvaluator:
    """
    Evaluates detection performance across refinement iterations I in {1, 2, 3}
    to reproduce Table V of the paper.
    """

    def __init__(self, c_min: int = 10, test_gen_fn: Optional[Callable] = None):
        self.c_min = c_min
        self.test_gen_fn = test_gen_fn

    def evaluate_iterations(
        self,
        dataset: List[DatasetRecord],
        max_iter: int = 3
    ) -> Dict[str, Any]:
        """
        Runs evaluation with i_max constrained to 1, 2, and 3 to observe progressive refinement.
        """
        iteration_results: Dict[int, Dict[str, float]] = {}

        for it in range(1, max_iter + 1):
            pipeline = SDHD_Pipeline(c_min=self.c_min, i_max=it)
            y_true: List[bool] = []
            y_pred: List[bool] = []

            for rec in dataset:
                y_true.append(rec.is_hallucinated)

                record_test_gen = None
                if rec.tests:
                    def _gen(r, c, f, cnt, _tests=rec.tests):
                        return _tests[:cnt] if len(_tests) >= cnt else _tests * (cnt // len(_tests) + 1)
                    record_test_gen = _gen
                elif self.test_gen_fn is not None:
                    record_test_gen = self.test_gen_fn

                report = pipeline.run(rec.prompt, rec.code, test_gen_fn=record_test_gen)
                is_hallu = report["summary"]["total_hallucinations"] > 0
                y_pred.append(is_hallu)

            metrics = calculate_metrics(y_true, y_pred)
            iteration_results[it] = metrics

        return iteration_results

    @staticmethod
    def generate_table5_markdown(results: Dict[int, Dict[str, float]]) -> str:
        """Renders Table V markdown."""
        lines = []
        lines.append("# Table V: Impact of Refinement Iterations (RQ3 Reproduction)")
        lines.append("")
        lines.append("| Iteration | Precision | Recall | F1 Score | Accuracy | FPR |")
        lines.append("| :---: | :---: | :---: | :---: | :---: | :---: |")
        for it, m in sorted(results.items()):
            lines.append(f"| **Iteration {it}** | {m['Precision']:.3f} | {m['Recall']:.3f} | **{m['F1']:.3f}** | {m['Accuracy']:.3f} | {m['FPR']:.3f} |")
        return "\n".join(lines)


# =====================================================================
# 2. Table VI: Runtime Latency & Efficiency Profiler
# =====================================================================

class RQ3EfficiencyProfiler:
    """
    Measures execution latency (Static vs Dynamic vs Total) per task and per dataset
    to reproduce Table VI of the paper.
    """

    def __init__(self, c_min: int = 10, i_max: int = 3, test_gen_fn: Optional[Callable] = None):
        self.c_min = c_min
        self.i_max = i_max
        self.test_gen_fn = test_gen_fn

    def profile_dataset(
        self,
        dataset_name: str,
        records: List[DatasetRecord]
    ) -> Dict[str, Any]:
        """Profiles static, dynamic, and total latency for a given dataset."""
        if not records:
            return {"count": 0, "avg_static_ms": 0.0, "avg_dynamic_ms": 0.0, "avg_total_ms": 0.0}

        static_times: List[float] = []
        dynamic_times: List[float] = []
        total_times: List[float] = []

        pipeline = SDHD_Pipeline(c_min=self.c_min, i_max=self.i_max)

        for rec in records:
            # 1. Static latency
            t0 = time.perf_counter()
            _ = detect_hallucinations(rec.code)
            t_static = (time.perf_counter() - t0) * 1000.0  # ms

            # 2. Full pipeline latency
            record_test_gen = None
            if rec.tests:
                def _gen(r, c, f, cnt, _tests=rec.tests):
                    return _tests[:cnt] if len(_tests) >= cnt else _tests * (cnt // len(_tests) + 1)
                record_test_gen = _gen
            elif self.test_gen_fn is not None:
                record_test_gen = self.test_gen_fn

            t0 = time.perf_counter()
            _ = pipeline.run(rec.prompt, rec.code, test_gen_fn=record_test_gen)
            t_total = (time.perf_counter() - t0) * 1000.0  # ms

            t_dynamic = max(0.0, t_total - t_static)

            static_times.append(t_static)
            dynamic_times.append(t_dynamic)
            total_times.append(t_total)

        n = len(records)
        return {
            "count": n,
            "avg_static_ms": round(sum(static_times) / n, 2),
            "avg_dynamic_ms": round(sum(dynamic_times) / n, 2),
            "avg_total_ms": round(sum(total_times) / n, 2),
            "throughput_tasks_per_sec": round(1000.0 / (sum(total_times) / n), 2) if sum(total_times) > 0 else 0.0
        }

    def profile_all(self, datasets: Dict[str, List[DatasetRecord]]) -> Dict[str, Dict[str, Any]]:
        """Profiles all datasets and combined pool."""
        report: Dict[str, Dict[str, Any]] = {}
        combined: List[DatasetRecord] = []
        for name, recs in datasets.items():
            report[name] = self.profile_dataset(name, recs)
            combined.extend(recs)
        report["Combined"] = self.profile_dataset("Combined", combined)
        return report

    @staticmethod
    def generate_table6_markdown(profile_data: Dict[str, Dict[str, Any]]) -> str:
        """Renders Table VI markdown."""
        lines = []
        lines.append("# Table VI: Computational Efficiency & Latency Breakdown (RQ3 Reproduction)")
        lines.append("")
        lines.append("| Dataset | Tasks Evaluated | Avg Static Time (ms) | Avg Dynamic Time (ms) | Avg Total Time (ms) | Throughput (tasks/s) |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for name, p in profile_data.items():
            lines.append(f"| **{name}** | {p['count']} | {p['avg_static_ms']} ms | {p['avg_dynamic_ms']} ms | **{p['avg_total_ms']} ms** | {p['throughput_tasks_per_sec']} |")
        return "\n".join(lines)


# =====================================================================
# 3. Figures 4 & 5: Hyperparameter Sensitivity Sweeper
# =====================================================================

class RQ3SensitivitySweeper:
    """
    Performs sensitivity sweeps over C_min (Figure 4) and I_max (Figure 5).
    """

    def __init__(self, test_gen_fn: Optional[Callable] = None):
        self.test_gen_fn = test_gen_fn

    def sweep_cmin(
        self,
        dataset: List[DatasetRecord],
        cmin_values: Optional[List[int]] = None
    ) -> Dict[int, Dict[str, float]]:
        """Sweeps C_min in {5, 10, 15, 20} (Figure 4)."""
        values = cmin_values or [5, 10, 15, 20]
        results: Dict[int, Dict[str, float]] = {}

        for c in values:
            pipeline = SDHD_Pipeline(c_min=c, i_max=3)
            y_true: List[bool] = []
            y_pred: List[bool] = []

            for rec in dataset:
                y_true.append(rec.is_hallucinated)
                record_test_gen = None
                if rec.tests:
                    def _gen(r, c_code, f, cnt, _tests=rec.tests):
                        return _tests[:cnt] if len(_tests) >= cnt else _tests * (cnt // len(_tests) + 1)
                    record_test_gen = _gen
                elif self.test_gen_fn is not None:
                    record_test_gen = self.test_gen_fn

                report = pipeline.run(rec.prompt, rec.code, test_gen_fn=record_test_gen)
                y_pred.append(report["summary"]["total_hallucinations"] > 0)

            results[c] = calculate_metrics(y_true, y_pred)

        return results

    def sweep_imax(
        self,
        dataset: List[DatasetRecord],
        imax_values: Optional[List[int]] = None
    ) -> Dict[int, Dict[str, float]]:
        """Sweeps I_max in {1, 2, 3, 4, 5} (Figure 5)."""
        values = imax_values or [1, 2, 3, 4, 5]
        results: Dict[int, Dict[str, float]] = {}

        for it in values:
            pipeline = SDHD_Pipeline(c_min=10, i_max=it)
            y_true: List[bool] = []
            y_pred: List[bool] = []

            for rec in dataset:
                y_true.append(rec.is_hallucinated)
                record_test_gen = None
                if rec.tests:
                    def _gen(r, c_code, f, cnt, _tests=rec.tests):
                        return _tests[:cnt] if len(_tests) >= cnt else _tests * (cnt // len(_tests) + 1)
                    record_test_gen = _gen
                elif self.test_gen_fn is not None:
                    record_test_gen = self.test_gen_fn

                report = pipeline.run(rec.prompt, rec.code, test_gen_fn=record_test_gen)
                y_pred.append(report["summary"]["total_hallucinations"] > 0)

            results[it] = calculate_metrics(y_true, y_pred)

        return results

    @staticmethod
    def generate_sensitivity_markdown(
        cmin_res: Dict[int, Dict[str, float]],
        imax_res: Dict[int, Dict[str, float]]
    ) -> str:
        """Renders Figures 4 & 5 data markdown tables."""
        lines = []
        lines.append("# Parameter Sensitivity Analysis (Figures 4 & 5 Reproduction)")
        lines.append("")
        lines.append("### Figure 4: Sensitivity to Coverage Threshold C_min")
        lines.append("| C_min Threshold | Precision | Recall | F1 Score | Accuracy |")
        lines.append("| :---: | :---: | :---: | :---: | :---: |")
        for c, m in sorted(cmin_res.items()):
            lines.append(f"| {c} | {m['Precision']:.3f} | {m['Recall']:.3f} | **{m['F1']:.3f}** | {m['Accuracy']:.3f} |")

        lines.append("")
        lines.append("### Figure 5: Sensitivity to Maximum Refinement Iterations I_max")
        lines.append("| I_max Iterations | Precision | Recall | F1 Score | Accuracy |")
        lines.append("| :---: | :---: | :---: | :---: | :---: |")
        for it, m in sorted(imax_res.items()):
            lines.append(f"| {it} | {m['Precision']:.3f} | {m['Recall']:.3f} | **{m['F1']:.3f}** | {m['Accuracy']:.3f} |")

        return "\n".join(lines)


# =====================================================================
# Full RQ3 Runner
# =====================================================================

def run_rq3_pipeline(
    output_dir: str = "results",
    test_gen_fn: Optional[Callable] = None
) -> Dict[str, Any]:
    """Executes the complete RQ3 evaluation suite and saves artifacts."""
    os.makedirs(output_dir, exist_ok=True)
    def _default_gen(reqs, code, feedback, count):
        return []
    active_gen = test_gen_fn or _default_gen

    data = load_all_datasets()
    combined_pool = data["MBPP"] + data["CodeHaluEval"] + data["HalluCode"]

    # 1. Table V Refinement
    print("[RQ3] Evaluating refinement progression (Table V)...")
    ref_evaluator = RQ3RefinementEvaluator(test_gen_fn=active_gen)
    table5_data = ref_evaluator.evaluate_iterations(combined_pool, max_iter=3)
    table5_md = ref_evaluator.generate_table5_markdown(table5_data)

    with open(os.path.join(output_dir, "table5_refinement.json"), "w", encoding="utf-8") as f:
        json.dump(table5_data, f, indent=2)
    with open(os.path.join(output_dir, "table5_refinement.md"), "w", encoding="utf-8") as f:
        f.write(table5_md)

    # 2. Table VI Efficiency
    print("[RQ3] Profiling execution efficiency (Table VI)...")
    eff_profiler = RQ3EfficiencyProfiler(test_gen_fn=active_gen)
    table6_data = eff_profiler.profile_all(data)
    table6_md = eff_profiler.generate_table6_markdown(table6_data)

    with open(os.path.join(output_dir, "table6_efficiency.json"), "w", encoding="utf-8") as f:
        json.dump(table6_data, f, indent=2)
    with open(os.path.join(output_dir, "table6_efficiency.md"), "w", encoding="utf-8") as f:
        f.write(table6_md)

    # 3. Figures 4 & 5 Sensitivity
    print("[RQ3] Sweeping C_min and I_max parameters (Figures 4 & 5)...")
    sweeper = RQ3SensitivitySweeper(test_gen_fn=active_gen)
    fig4_data = sweeper.sweep_cmin(combined_pool, [5, 10, 15, 20])
    fig5_data = sweeper.sweep_imax(combined_pool, [1, 2, 3, 4, 5])
    fig_md = sweeper.generate_sensitivity_markdown(fig4_data, fig5_data)

    sensitivity_report = {
        "figure_4_cmin_sensitivity": fig4_data,
        "figure_5_imax_sensitivity": fig5_data
    }
    with open(os.path.join(output_dir, "figures_4_5_sensitivity.json"), "w", encoding="utf-8") as f:
        json.dump(sensitivity_report, f, indent=2)
    with open(os.path.join(output_dir, "figures_4_5_sensitivity.md"), "w", encoding="utf-8") as f:
        f.write(fig_md)

    print(f"[RQ3] Evaluation complete! Artifacts saved to {output_dir}/")
    return {
        "table5": table5_data,
        "table6": table6_data,
        "sensitivity": sensitivity_report
    }


if __name__ == "__main__":
    rep = run_rq3_pipeline()
    print("\n--- Table V ---\n" + RQ3RefinementEvaluator.generate_table5_markdown(rep["table5"]))
    print("\n--- Table VI ---\n" + RQ3EfficiencyProfiler.generate_table6_markdown(rep["table6"]))
    print("\n--- Sensitivity ---\n" + RQ3SensitivitySweeper.generate_sensitivity_markdown(
        rep["sensitivity"]["figure_4_cmin_sensitivity"],
        rep["sensitivity"]["figure_5_imax_sensitivity"]
    ))
