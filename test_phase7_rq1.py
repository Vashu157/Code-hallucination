"""
test_phase7_rq1.py - Unit & Comparative Tests for Phase 7 (RQ1 Evaluation & Table III Reproduction)
===================================================================================================
Validates Section IV-C and Table III of the SDHD paper:
1. RQ1 Multi-Dataset Benchmark Execution (MBPP, CodeHaluEval, HalluCode, Combined)
2. 4-Method Comparison (SDHD, CodeHalu, SelfCheck, SAC3)
3. Table III Markdown and JSON Generation
4. Statistical Significance Testing (McNemar paired comparison)
"""

import unittest
from dataset_loaders import DatasetRecord, load_all_datasets
from evaluate_rq1 import RQ1Evaluator, run_rq1_pipeline


class TestPhase7RQ1(unittest.TestCase):

    def setUp(self):
        def _mock_gen(reqs, code, feedback, count):
            return [{"input": [1, 2], "expected_output": 3}] * count
        self.evaluator = RQ1Evaluator(test_gen_fn=_mock_gen)
        self.mock_dataset = {
            "MBPP": [
                DatasetRecord(
                    task_id="m1", dataset="MBPP", prompt="Add 2 nums",
                    code="def add(a, b): return a + b",
                    tests=[{"input": [1, 2], "expected_output": 3}],
                    is_hallucinated=False
                )
            ],
            "CodeHaluEval": [
                DatasetRecord(
                    task_id="c1", dataset="CodeHaluEval", prompt="Multiply 2 nums",
                    code="def mul(a, b): return a + b",  # Buggy logic
                    tests=[{"input": [2, 3], "expected_output": 6}],
                    is_hallucinated=True
                )
            ],
            "HalluCode": [
                DatasetRecord(
                    task_id="h1", dataset="HalluCode", prompt="Use undefined var",
                    code="def test(): return unknown_var + 1",
                    tests=[],
                    is_hallucinated=True
                )
            ]
        }

    def test_rq1_evaluator_execution(self):
        """Validates that RQ1 evaluator executes all 4 methods across splits."""
        benchmark_report = self.evaluator.run_full_benchmark(self.mock_dataset)
        splits = benchmark_report["splits"]

        # Check all splits are present
        self.assertIn("MBPP", splits)
        self.assertIn("CodeHaluEval", splits)
        self.assertIn("HalluCode", splits)
        self.assertIn("Combined", splits)

        # Check all 4 methods are evaluated on Combined split
        combined = splits["Combined"]
        for method in ["SDHD", "CodeHalu", "SelfCheck", "SAC3"]:
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
        self.assertIn("CodeHalu", md_text)
        self.assertIn("SelfCheck", md_text)
        self.assertIn("SAC3", md_text)
        self.assertIn("Statistical Significance", md_text)

    def test_significance_testing(self):
        """Validates McNemar statistical calculation."""
        sdhd_recs = [
            {"task_id": 1, "ground_truth": True, "predicted": True},   # Correct
            {"task_id": 2, "ground_truth": True, "predicted": True},   # Correct
            {"task_id": 3, "ground_truth": False, "predicted": False}, # Correct
            {"task_id": 4, "ground_truth": False, "predicted": False}, # Correct
        ]
        base_recs = [
            {"task_id": 1, "ground_truth": True, "predicted": False},  # Incorrect (SDHD win)
            {"task_id": 2, "ground_truth": True, "predicted": False},  # Incorrect (SDHD win)
            {"task_id": 3, "ground_truth": False, "predicted": True},  # Incorrect (SDHD win)
            {"task_id": 4, "ground_truth": False, "predicted": False}, # Correct (Tie)
        ]

        sig = self.evaluator.compute_paired_significance(sdhd_recs, base_recs)
        self.assertEqual(sig["sdhd_win"], 3)
        self.assertEqual(sig["baseline_win"], 0)
        self.assertEqual(sig["tie_correct"], 1)
        self.assertEqual(sig["tie_wrong"], 0)
        self.assertGreater(sig["chi2_stat"], 0.0)
        self.assertIn("p_value", sig)
        self.assertIn("statistically_significant", sig)

    def test_metrics_reproducibility(self):
        """Validates that running the pipeline produces consistent, serializable output."""
        all_data = load_all_datasets()
        # Small sample for speed
        sample_pool = {
            "MBPP": all_data["MBPP"][:2],
            "CodeHaluEval": all_data["CodeHaluEval"][:2],
            "HalluCode": all_data["HalluCode"][:2],
        }
        res1 = self.evaluator.run_full_benchmark(sample_pool)
        res2 = self.evaluator.run_full_benchmark(sample_pool)

        self.assertEqual(
            res1["splits"]["Combined"]["SDHD"]["metrics"],
            res2["splits"]["Combined"]["SDHD"]["metrics"]
        )


if __name__ == "__main__":
    unittest.main()
