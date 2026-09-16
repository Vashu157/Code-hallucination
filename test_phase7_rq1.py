"""
test_phase7_rq1.py - Unit & Comparative Tests for Phase 7 (RQ1 Evaluation & Tables III, IV, VII Reproduction)
=============================================================================================================
Validates Section IV-C and Tables III, IV, VII of the SDHD paper:
1. Match Criteria (Type matching, +-1 line tolerance, identifier substring match)
2. RQ1 Multi-Dataset Benchmark Execution (MBPP, CodeHaluEval, HalluCode, Combined)
3. Table III Markdown and JSON Generation + McNemar Paired Significance
4. Table IV Clean-Code False Positive Rate (FPR) Evaluation & Markdown Generation
5. Table VII 8-Type Hallucination Category Breakdown Matrix & Markdown Generation
6. Consolidated Summary Report & Full Pipeline Output Generation
"""

import os
import tempfile
import unittest
from baselines import BaseBaseline, calculate_metrics
from dataset_loaders import DatasetRecord
from evaluate_rq1 import (
    RQ1Evaluator,
    match_detection_to_ground_truth,
    run_rq1_pipeline
)


class MockDetector(BaseBaseline):
    """Deterministic mock detector for fast unit testing."""
    def __init__(self, name: str, flag_pattern: str, error_type: str = "IH"):
        self.name = name
        self.flag_pattern = flag_pattern
        self.error_type = error_type

    def detect(self, prompt: str, code: str, tests=None, **kwargs):
        if self.flag_pattern in code:
            return {
                "is_hallucinated": True,
                "confidence": 0.9,
                "method": self.name,
                "detections": [{
                    "type_code": self.error_type,
                    "error_type": f"{self.error_type} error",
                    "location": "test_var",
                    "line_number": 2,
                    "detail": "Mock detection"
                }],
                "details": {}
            }
        return {
            "is_hallucinated": False,
            "confidence": 0.1,
            "method": self.name,
            "detections": [],
            "details": {}
        }


class TestPhase7RQ1(unittest.TestCase):

    def setUp(self):
        # Deterministic mock detectors
        self.det_sdhd = MockDetector("SDHD", "bug", error_type="IH")
        self.det_baseline1 = MockDetector("Baseline1", "bug_b1", error_type="IH")
        self.det_baseline2 = MockDetector("Baseline2", "always_clean", error_type="IH")

        self.evaluator = RQ1Evaluator(
            detectors=[self.det_sdhd, self.det_baseline1, self.det_baseline2],
            timeout=1
        )

        self.mock_dataset = {
            "MBPP": [
                DatasetRecord(
                    task_id="m1", dataset="MBPP", prompt="Add 2 nums",
                    code="def add(a, b): return a + b",
                    tests=[{"input": [1, 2], "expected_output": 3}],
                    is_hallucinated=False
                ),
                DatasetRecord(
                    task_id="m2", dataset="MBPP", prompt="Add numbers clean",
                    code="def add2(a, b): return a + b",
                    tests=[],
                    is_hallucinated=False
                )
            ],
            "CodeHaluEval": [
                DatasetRecord(
                    task_id="c1", dataset="CodeHaluEval", prompt="Multiply 2 nums",
                    code="def mul(a, b): return bug",
                    tests=[{"input": [2, 3], "expected_output": 6}],
                    ground_truth_labels=[{
                        "type_code": "LDH",
                        "error_type": "Logical Deviation Hallucination (LDH)",
                        "location": "mul",
                        "line_number": 2
                    }],
                    is_hallucinated=True
                )
            ],
            "HalluCode": [
                DatasetRecord(
                    task_id="h1", dataset="HalluCode", prompt="Use undefined var",
                    code="def test(): return bug",
                    tests=[],
                    ground_truth_labels=[{
                        "type_code": "IH",
                        "error_type": "Identity Hallucination (IH)",
                        "location": "test_var",
                        "line_number": 2
                    }],
                    is_hallucinated=True
                ),
                DatasetRecord(
                    task_id="h2", dataset="HalluCode", prompt="Clean code in HalluCode",
                    code="def clean(): return 42",
                    tests=[],
                    ground_truth_labels=[],
                    is_hallucinated=False
                )
            ]
        }

    def test_match_criteria(self):
        """Validates fine-grained match criteria (type match, line tolerance, identifier substring)."""
        gt_ih = {
            "type_code": "IH",
            "error_type": "Identity Hallucination (IH)",
            "location": "factor",
            "line_number": 5
        }

        # 1. Exact match
        det_exact = {"type_code": "IH", "location": "factor", "line_number": 5}
        self.assertTrue(match_detection_to_ground_truth(det_exact, gt_ih))

        # 2. Line number within +- 1 line tolerance
        det_line_tolerance = {"type_code": "IH", "location": "factor", "line_number": 6}
        self.assertTrue(match_detection_to_ground_truth(det_line_tolerance, gt_ih))

        # 3. Line number beyond tolerance -> still matches if location identifier matches
        det_line_far = {"type_code": "IH", "location": "factor", "line_number": 12}
        self.assertTrue(match_detection_to_ground_truth(det_line_far, gt_ih))

        # 4. Type mismatch -> False
        det_mismatch_type = {"type_code": "SAH", "location": "factor", "line_number": 5}
        self.assertFalse(match_detection_to_ground_truth(det_mismatch_type, gt_ih))

        # 5. Dynamic flex matching (LDH vs LFH)
        gt_ldh = {"type_code": "LDH", "error_type": "Logical Deviation Hallucination (LDH)"}
        det_lfh = {"type_code": "LFH", "error_type": "Logical Failure Hallucination (LFH)"}
        self.assertTrue(match_detection_to_ground_truth(det_lfh, gt_ldh))

    def test_rq1_evaluator_execution(self):
        """Validates that RQ1 evaluator executes all methods across splits for Table III."""
        benchmark_report = self.evaluator.run_full_benchmark(self.mock_dataset)
        splits = benchmark_report["splits"]

        self.assertIn("MBPP", splits)
        self.assertIn("CodeHaluEval", splits)
        self.assertIn("HalluCode", splits)
        self.assertIn("Combined", splits)

        combined = splits["Combined"]
        for method in ["SDHD", "Baseline1", "Baseline2"]:
            self.assertIn(method, combined)
            m = combined[method]["metrics"]
            self.assertIn("Precision", m)
            self.assertIn("Recall", m)
            self.assertIn("F1", m)
            self.assertIn("Accuracy", m)
            self.assertIn("FPR", m)

    def test_table3_markdown_generation(self):
        """Validates Table III Markdown formatting matches paper specifications."""
        benchmark_report = self.evaluator.run_full_benchmark(self.mock_dataset)
        md_text = self.evaluator.generate_table3_markdown(benchmark_report)

        self.assertIn("# Table III: Hallucination Detection Performance", md_text)
        self.assertIn("| Dataset | Method | Precision | Recall | F1 Score | Accuracy | FPR |", md_text)
        self.assertIn("SDHD", md_text)
        self.assertIn("Baseline1", md_text)
        self.assertIn("Statistical Significance", md_text)

    def test_table4_clean_code_fpr(self):
        """Validates Table IV clean code False Positive Rate evaluation."""
        mbpp_pool = self.mock_dataset["MBPP"]
        clean_res = self.evaluator.evaluate_table4_clean_fpr(mbpp_pool)

        self.assertIn("SDHD", clean_res)
        self.assertIn("Baseline1", clean_res)

        sdhd_clean = clean_res["SDHD"]
        self.assertEqual(sdhd_clean["total_clean"], 2)
        self.assertEqual(sdhd_clean["FP"], 0)
        self.assertEqual(sdhd_clean["TN"], 2)
        self.assertEqual(sdhd_clean["FPR"], 0.0)
        self.assertEqual(sdhd_clean["Specificity"], 1.0)

        # Markdown formatting
        md_table4 = self.evaluator.generate_table4_markdown(clean_res)
        self.assertIn("# Table IV: Clean-Code False Positive Rate", md_table4)
        self.assertIn("| Method | Clean Tasks | False Positives (FP) | True Negatives (TN) | FPR (%) | Specificity (%) |", md_table4)
        self.assertIn("SDHD", md_table4)

    def test_table7_category_breakdown(self):
        """Validates Table VII 8-type hallucination category breakdown matrix."""
        all_records = []
        for recs in self.mock_dataset.values():
            all_records.extend(recs)

        cat_breakdown = self.evaluator.evaluate_table7_category_breakdown(all_records)
        categories = cat_breakdown["categories"]

        # Check all 8 types are present
        for code in ["IH", "ESH", "DCH", "SAH", "PCH", "CBH", "LDH", "LFH"]:
            self.assertIn(code, categories)

        # In mock data, task h1 has GT IH
        self.assertEqual(categories["IH"]["gt_count"], 1)
        # SDHD detects 'bug' which is in h1
        self.assertEqual(categories["IH"]["caught"]["SDHD"], 1)
        self.assertEqual(categories["IH"]["recall"]["SDHD"], 1.0)

        # Markdown formatting
        md_table7 = self.evaluator.generate_table7_markdown(cat_breakdown)
        self.assertIn("# Table VII: Hallucination Category Breakdown Matrix", md_table7)
        self.assertIn("| Code | Hallucination Category | Ground Truth |", md_table7)
        self.assertIn("SDHD", md_table7)

    def test_significance_testing(self):
        """Validates McNemar continuity-corrected statistical calculation."""
        sdhd_recs = [
            {"task_id": 1, "ground_truth": True, "predicted": True},
            {"task_id": 2, "ground_truth": True, "predicted": True},
            {"task_id": 3, "ground_truth": False, "predicted": False},
            {"task_id": 4, "ground_truth": False, "predicted": False},
        ]
        base_recs = [
            {"task_id": 1, "ground_truth": True, "predicted": False},  # SDHD win
            {"task_id": 2, "ground_truth": True, "predicted": False},  # SDHD win
            {"task_id": 3, "ground_truth": False, "predicted": True},  # SDHD win
            {"task_id": 4, "ground_truth": False, "predicted": False}, # Tie
        ]

        sig = self.evaluator.compute_paired_significance(sdhd_recs, base_recs)
        self.assertEqual(sig["sdhd_win"], 3)
        self.assertEqual(sig["baseline_win"], 0)
        self.assertEqual(sig["tie_correct"], 1)
        self.assertEqual(sig["tie_wrong"], 0)
        self.assertGreater(sig["chi2_stat"], 0.0)
        self.assertIn("p_value", sig)
        self.assertIn("statistically_significant", sig)

    def test_run_rq1_pipeline_artifacts(self):
        """Validates that run_rq1_pipeline outputs all expected files into output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            def _mock_gen(reqs, code, feedback, count):
                return []
            res_dict, summary = run_rq1_pipeline(
                output_dir=tmpdir,
                include_all_baselines=False,
                test_gen_fn=_mock_gen
            )

            self.assertIn("table3", res_dict)
            self.assertIn("table4", res_dict)
            self.assertIn("table7", res_dict)

            # Check files exist
            expected_files = [
                "table3_reproduction.json", "table3_reproduction.md",
                "table4_clean_fpr.json", "table4_clean_fpr.md",
                "table7_reproduction.json", "table7_reproduction.md",
                "rq1_summary_report.md"
            ]
            for ef in expected_files:
                fpath = os.path.join(tmpdir, ef)
                self.assertTrue(os.path.exists(fpath), f"Expected artifact {ef} was not generated.")


if __name__ == "__main__":
    unittest.main()
