"""
ablation.py - RQ2 Ablation Study & Table IV Reproduction (Section IV-D)
=======================================================================
Reproduces RQ2 from the SDHD paper:
"What are the individual contributions of the static analysis module (O1) and
dynamic execution module (O2) to SDHD's overall detection capability?"

Evaluates:
  - SDHD-S (Static-only detector, O1)
  - SDHD-D (Dynamic-only detector, O2)
  - SDHD (Full hybrid, O1 U O2)

Across:
  - MBPP (Clean-code pool)
  - CodeHaluEval (Dynamic benchmark)
  - HalluCode (Static benchmark)
  - Combined Benchmark (Overall aggregate)

Outputs:
  - Table IV formatted in Markdown and JSON
  - Precision, Recall, F1 Score, Accuracy, False Positive Rate (FPR)
"""

import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Callable

from baselines import (
    BaseBaseline,
    SDHDBaselineAdapter,
    calculate_metrics,
    evaluate_detector
)
from dataset_loaders import DatasetRecord, load_all_datasets
from static_analysis import detect_hallucinations
from sdhd_pipeline import SDHD_Pipeline, normalize_hallucination_record


# =====================================================================
# 1. SDHD-S: Static-Only Detector (O1)
# =====================================================================

class SDHDStaticOnlyDetector(BaseBaseline):
    """
    SDHD-S: Static-Only Detector (Section IV-D).
    Evaluates only Stage 1 static analysis (O1) via SSA + AST analysis.
    Ignores dynamic execution and test cases.
    """
    name: str = "SDHD-S"

    def detect(self, prompt: str, code: str, **kwargs) -> Dict[str, Any]:
        raw_errors = detect_hallucinations(code)
        normalized = [normalize_hallucination_record(err, default_source="static") for err in raw_errors]
        is_hallu = len(normalized) > 0
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "details": {
                "static_count": len(normalized),
                "detections": normalized
            }
        }


# =====================================================================
# 2. SDHD-D: Dynamic-Only Detector (O2)
# =====================================================================

class SDHDDynamicOnlyDetector(BaseBaseline):
    """
    SDHD-D: Dynamic-Only Detector (Section IV-D).
    Evaluates only Stage 2 dynamic execution and feedback refinement (O2) via Algorithm 3.
    Ignores static analysis.
    """
    name: str = "SDHD-D"

    def __init__(
        self,
        timeout: int = 5,
        c_min: int = 10,
        i_max: int = 3
    ):
        self.pipeline = SDHD_Pipeline(timeout=timeout, c_min=c_min, i_max=i_max)

    def detect(
        self,
        prompt: str,
        code: str,
        test_gen_fn: Optional[Callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        dyn_res = self.pipeline._run_dynamic_pipeline(
            user_prompt=prompt,
            generated_code=code,
            test_gen_fn=test_gen_fn
        )
        hallus = dyn_res.get("hallucinations", [])
        is_hallu = len(hallus) > 0 or dyn_res.get("status") == "POTENTIAL_HALLUCINATION"
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "details": {
                "dynamic_status": dyn_res.get("status"),
                "dynamic_count": len(hallus),
                "iterations": dyn_res.get("iterations", 0),
                "test_cases_run": dyn_res.get("test_cases_run", 0),
                "detections": hallus
            }
        }


# =====================================================================
# 3. RQ2 Ablation Evaluator & Table IV Generator
# =====================================================================

class RQ2AblationEvaluator:
    """
    Orchestrates the evaluation of SDHD-S vs SDHD-D vs full SDHD to reproduce Table IV.
    """

    def __init__(
        self,
        timeout: int = 5,
        c_min: int = 10,
        i_max: int = 3,
        test_gen_fn: Optional[Callable] = None
    ):
        self.test_gen_fn = test_gen_fn
        self.detectors: List[BaseBaseline] = [
            SDHDStaticOnlyDetector(),
            SDHDDynamicOnlyDetector(timeout=timeout, c_min=c_min, i_max=i_max),
            SDHDBaselineAdapter(pipeline=SDHD_Pipeline(timeout=timeout, c_min=c_min, i_max=i_max))
        ]

    def evaluate_on_dataset(
        self,
        dataset_name: str,
        records: List[DatasetRecord]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Evaluates all 3 ablation detectors on a given dataset split.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for detector in self.detectors:
            eval_res = evaluate_detector(detector, records, test_gen_fn=self.test_gen_fn)
            results[detector.name] = eval_res
        return results

    def run_full_ablation(
        self,
        datasets: Optional[Dict[str, List[DatasetRecord]]] = None
    ) -> Dict[str, Any]:
        """
        Runs the ablation study across MBPP, CodeHaluEval, HalluCode, and Combined.
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

        ablation_results: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for split_name, recs in eval_splits.items():
            if recs:
                ablation_results[split_name] = self.evaluate_on_dataset(split_name, recs)

        return {"splits": ablation_results}

    @staticmethod
    def generate_table4_markdown(ablation_data: Dict[str, Any]) -> str:
        """
        Renders the ablation results as a clean Markdown table matching Table IV.
        """
        lines = []
        lines.append("# Table IV: Ablation Study of SDHD Components (RQ2 Reproduction)")
        lines.append("")
        lines.append("| Dataset | Method | Precision | Recall | F1 Score | Accuracy | FPR |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: |")

        splits_order = ["MBPP", "CodeHaluEval", "HalluCode", "Combined"]
        methods_order = ["SDHD-S", "SDHD-D", "SDHD"]

        splits_data = ablation_data.get("splits", {})

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
                is_full = (method == "SDHD")
                method_label = f"**{method}**" if is_full else method
                lines.append(f"| **{split}** | {method_label} | {p} | {r} | **{f1}** | {acc} | {fpr} |")

        return "\n".join(lines)


def run_rq2_pipeline(
    output_dir: str = "results",
    test_gen_fn: Optional[Callable] = None
) -> Tuple[Dict[str, Any], str]:
    """
    Executes the entire RQ2 ablation benchmark and saves output files.
    """
    os.makedirs(output_dir, exist_ok=True)
    def _default_gen(reqs, code, feedback, count):
        return []
    active_gen = test_gen_fn or _default_gen
    evaluator = RQ2AblationEvaluator(test_gen_fn=active_gen)
    data = load_all_datasets()

    print("[RQ2] Running full ablation study (SDHD-S vs SDHD-D vs SDHD)...")
    ablation_report = evaluator.run_full_ablation(data)
    md_table = evaluator.generate_table4_markdown(ablation_report)

    # Save JSON and Markdown artifacts
    json_path = os.path.join(output_dir, "table4_ablation.json")
    md_path = os.path.join(output_dir, "table4_ablation.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(ablation_report, f, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_table)

    print(f"[RQ2] Ablation complete! Artifacts saved to:\n  - {json_path}\n  - {md_path}")
    return ablation_report, md_table


if __name__ == "__main__":
    rep, table = run_rq2_pipeline()
    print("\n" + table)
