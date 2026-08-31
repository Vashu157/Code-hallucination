"""
evaluate_rq1.py - RQ1 Evaluation Runner & Table III Reproduction (Section IV-C)
==============================================================================
Reproduces RQ1 from the SDHD paper:
"How effective is SDHD in detecting LLM hallucinations compared to existing methods?"

Evaluates:
  - SDHD (Hybrid Static + Dynamic)
  - CodeHalu (Tian et al. [17])
  - SelfCheck (Li et al. [22])
  - SAC3 (Manakul et al. [23])

Across Benchmark Datasets:
  - MBPP (Clean-code pool for FPR / Precision)
  - CodeHaluEval (Dynamic benchmark)
  - HalluCode (Static benchmark)
  - Combined Benchmark (Overall aggregate)

Outputs:
  - Table III formatted in Markdown and JSON
  - Precision (P), Recall (R), F1, Accuracy (Acc), False Positive Rate (FPR)
  - Statistical Significance Tests (Paired difference analysis)
"""

import json
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from baselines import (
    BaseBaseline,
    CodeHaluBaseline,
    SelfCheckBaseline,
    SAC3Baseline,
    SDHDBaselineAdapter,
    calculate_metrics,
    evaluate_detector
)
from dataset_loaders import DatasetRecord, load_all_datasets


class RQ1Evaluator:
    """
    Orchestrates the evaluation of SDHD against CodeHalu, SelfCheck, and SAC3
    to reproduce Table III of the paper.
    """

    def __init__(
        self,
        detectors: Optional[List[BaseBaseline]] = None,
        timeout: int = 5,
        c_min: int = 10,
        i_max: int = 3,
        test_gen_fn: Optional[Any] = None
    ):
        self.timeout = timeout
        self.c_min = c_min
        self.i_max = i_max
        self.test_gen_fn = test_gen_fn

        if detectors is not None:
            self.detectors = detectors
        else:
            self.detectors = [
                SDHDBaselineAdapter(),
                CodeHaluBaseline(timeout=timeout),
                SelfCheckBaseline(threshold=0.65),
                SAC3Baseline(threshold=0.40)
            ]

    def evaluate_on_dataset(
        self,
        dataset_name: str,
        records: List[DatasetRecord]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Evaluates all detectors on a specific dataset split.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for detector in self.detectors:
            eval_res = evaluate_detector(detector, records, test_gen_fn=self.test_gen_fn)
            results[detector.name] = eval_res
        return results

    def run_full_benchmark(
        self,
        datasets: Optional[Dict[str, List[DatasetRecord]]] = None
    ) -> Dict[str, Any]:
        """
        Runs the full RQ1 benchmark across MBPP, CodeHaluEval, HalluCode, and Combined.
        """
        data_dict = datasets or load_all_datasets()

        combined_records: List[DatasetRecord] = []
        for dname, recs in data_dict.items():
            combined_records.extend(recs)

        eval_splits: Dict[str, List[DatasetRecord]] = {
            "MBPP": data_dict.get("MBPP", []),
            "CodeHaluEval": data_dict.get("CodeHaluEval", []),
            "HalluCode": data_dict.get("HalluCode", []),
            "Combined": combined_records
        }

        benchmark_results: Dict[str, Dict[str, Dict[str, Any]]] = {}

        for split_name, recs in eval_splits.items():
            if recs:
                benchmark_results[split_name] = self.evaluate_on_dataset(split_name, recs)

        # Statistical significance comparison (SDHD vs Baselines on Combined split)
        significance = {}
        if "Combined" in benchmark_results and "SDHD" in benchmark_results["Combined"]:
            sdhd_records = benchmark_results["Combined"]["SDHD"]["records"]
            for d in self.detectors:
                if d.name != "SDHD" and d.name in benchmark_results["Combined"]:
                    base_records = benchmark_results["Combined"][d.name]["records"]
                    sig_res = self.compute_paired_significance(sdhd_records, base_records)
                    significance[f"SDHD_vs_{d.name}"] = sig_res

        return {
            "splits": benchmark_results,
            "significance": significance
        }

    @staticmethod
    def compute_paired_significance(
        sdhd_records: List[Dict[str, Any]],
        baseline_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Computes paired accuracy comparison and McNemar's / paired difference statistic.
        """
        # Align by task_id
        base_map = {r["task_id"]: r for r in baseline_records}
        
        # b: SDHD correct, Baseline incorrect
        # c: SDHD incorrect, Baseline correct
        b = 0
        c = 0
        both_correct = 0
        both_wrong = 0

        for r_sdhd in sdhd_records:
            tid = r_sdhd["task_id"]
            gt = r_sdhd["ground_truth"]
            sdhd_correct = (r_sdhd["predicted"] == gt)
            
            r_base = base_map.get(tid)
            if r_base is not None:
                base_correct = (r_base["predicted"] == gt)
                if sdhd_correct and not base_correct:
                    b += 1
                elif not sdhd_correct and base_correct:
                    c += 1
                elif sdhd_correct and base_correct:
                    both_correct += 1
                else:
                    both_wrong += 1

        # McNemar test statistic: (b - c)^2 / (b + c)
        discordant = b + c
        if discordant > 0:
            chi2_stat = ((abs(b - c) - 1) ** 2) / discordant  # with continuity correction
            # Approximate p-value from chi-square distribution with df=1: p = erfc(sqrt(chi2 / 2))
            p_val = math.erfc(math.sqrt(max(0.0, chi2_stat) / 2.0))
        else:
            chi2_stat = 0.0
            p_val = 1.0

        return {
            "sdhd_win": b,
            "baseline_win": c,
            "tie_correct": both_correct,
            "tie_wrong": both_wrong,
            "chi2_stat": round(chi2_stat, 4),
            "p_value": round(p_val, 6),
            "statistically_significant": p_val < 0.05
        }

    @staticmethod
    def generate_table3_markdown(benchmark_data: Dict[str, Any]) -> str:
        """
        Renders the benchmark results as a clean Markdown table matching Table III.
        """
        lines = []
        lines.append("# Table III: Hallucination Detection Performance (RQ1 Reproduction)")
        lines.append("")
        lines.append("| Dataset | Method | Precision | Recall | F1 Score | Accuracy | FPR |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: |")

        splits_order = ["MBPP", "CodeHaluEval", "HalluCode", "Combined"]
        methods_order = ["SDHD", "CodeHalu", "SelfCheck", "SAC3"]

        splits_data = benchmark_data.get("splits", {})

        for split in splits_order:
            if split not in splits_data:
                continue
            for method in methods_order:
                if method not in splits_data[split]:
                    continue
                m = splits_data[split][method]["metrics"]
                p = f"{m['Precision']:.3f}"
                r = f"{m['Recall']:.3f}"
                f1 = f"{m['F1']:.3f}"
                acc = f"{m['Accuracy']:.3f}"
                fpr = f"{m['FPR']:.3f}"
                lines.append(f"| **{split}** | **{method}** | {p} | {r} | **{f1}** | {acc} | {fpr} |")

        lines.append("")
        lines.append("### Statistical Significance (McNemar Test on Combined Split)")
        sig_data = benchmark_data.get("significance", {})
        if sig_data:
            lines.append("| Comparison | SDHD Wins | Baseline Wins | Chi² Stat | p-value | Significant (p < 0.05) |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
            for comp, s in sig_data.items():
                sig_str = "Yes (p < 0.05)" if s["statistically_significant"] else "No"
                lines.append(f"| {comp} | {s['sdhd_win']} | {s['baseline_win']} | {s['chi2_stat']} | {s['p_value']} | {sig_str} |")
        else:
            lines.append("No significance data available.")

        return "\n".join(lines)


def run_rq1_pipeline(
    output_dir: str = "results",
    test_gen_fn: Optional[Any] = None
) -> Tuple[Dict[str, Any], str]:
    """
    Executes the entire RQ1 benchmark and saves output files.
    """
    os.makedirs(output_dir, exist_ok=True)
    def _default_gen(reqs, code, feedback, count):
        return []
    active_gen = test_gen_fn or _default_gen
    evaluator = RQ1Evaluator(test_gen_fn=active_gen)
    data = load_all_datasets()


    print("[RQ1] Running full multi-dataset baseline evaluation...")
    benchmark_report = evaluator.run_full_benchmark(data)
    md_table = evaluator.generate_table3_markdown(benchmark_report)

    # Save JSON and Markdown artifacts
    json_path = os.path.join(output_dir, "table3_reproduction.json")
    md_path = os.path.join(output_dir, "table3_reproduction.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(benchmark_report, f, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_table)

    print(f"[RQ1] Evaluation complete! Artifacts saved to:\n  - {json_path}\n  - {md_path}")
    return benchmark_report, md_table


if __name__ == "__main__":
    rep, table = run_rq1_pipeline()
    print("\n" + table)
