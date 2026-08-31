"""
test_phase8_ablation.py - Unit & Comparative Tests for Phase 8 (RQ2 Ablation Study)
===================================================================================
Validates Section IV-D and Table IV of the SDHD paper:
1. SDHD-S (Static-Only Detector O1)
2. SDHD-D (Dynamic-Only Detector O2)
3. SDHD (Full Hybrid Detector O1 U O2)
4. Table IV Markdown and JSON Generation
"""

import unittest
from dataset_loaders import DatasetRecord, load_all_datasets
from ablation import (
    SDHDStaticOnlyDetector,
    SDHDDynamicOnlyDetector,
    RQ2AblationEvaluator,
    run_rq2_pipeline
)
from baselines import SDHDBaselineAdapter


class TestPhase8Ablation(unittest.TestCase):

    def setUp(self):
        def _mock_gen(reqs, code, feedback, count):
            return [{"input": [1, 2], "expected_output": 3}] * count
        self.mock_gen = _mock_gen
        self.evaluator = RQ2AblationEvaluator(test_gen_fn=_mock_gen)

        # 1 static-only bug (unimported module ESH), 1 dynamic-only bug (wrong logic LDH)
        self.static_bug_code = "def test(): return math.sqrt(16)"  # math unimported (ESH)
        self.dynamic_bug_code = "def add(a, b): return a * b"     # wrong add logic (LDH)
        self.clean_code = "def add(a, b): return a + b"

    def test_static_only_detector(self):
        """Validates SDHD-S catches static bugs but misses dynamic logic bugs."""
        detector = SDHDStaticOnlyDetector()

        # Static bug -> detected
        res_static = detector.detect("Compute sqrt", self.static_bug_code)
        self.assertEqual(res_static["method"], "SDHD-S")
        self.assertTrue(res_static["is_hallucinated"])

        # Clean code -> not detected
        res_clean = detector.detect("Add numbers", self.clean_code)
        self.assertFalse(res_clean["is_hallucinated"])

        # Pure dynamic bug (valid syntax/SSA) -> missed by static detector
        res_dynamic = detector.detect("Add numbers", self.dynamic_bug_code)
        self.assertFalse(res_dynamic["is_hallucinated"])

    def test_dynamic_only_detector(self):
        """Validates SDHD-D catches dynamic test failures but misses static bugs when tests are empty."""
        detector = SDHDDynamicOnlyDetector()

        # Dynamic bug with failing test -> detected
        dynamic_tests = [{"input": [2, 3], "expected_output": 5}]
        def failing_gen(r, c, f, count):
            return dynamic_tests * count

        res_dynamic = detector.detect("Add numbers", self.dynamic_bug_code, test_gen_fn=failing_gen)
        self.assertEqual(res_dynamic["method"], "SDHD-D")
        self.assertTrue(res_dynamic["is_hallucinated"])

        # Clean code with passing test -> not detected
        clean_tests = [{"input": [2, 3], "expected_output": 5}]
        def passing_gen(r, c, f, count):
            return clean_tests * count

        res_clean = detector.detect("Add numbers", self.clean_code, test_gen_fn=passing_gen)
        self.assertFalse(res_clean["is_hallucinated"])

    def test_hybrid_synergy(self):
        """Validates that full SDHD catches BOTH static and dynamic bugs."""
        sdhd = SDHDBaselineAdapter()

        # Catches static bug (even without tests)
        def empty_gen(r, c, f, count):
            return []
        res_static = sdhd.detect("Compute sqrt", self.static_bug_code, test_gen_fn=empty_gen)
        self.assertTrue(res_static["is_hallucinated"])

        # Catches dynamic bug
        dynamic_tests = [{"input": [2, 3], "expected_output": 5}]
        def failing_gen(r, c, f, count):
            return dynamic_tests * count
        res_dynamic = sdhd.detect("Add numbers", self.dynamic_bug_code, test_gen_fn=failing_gen)
        self.assertTrue(res_dynamic["is_hallucinated"])

    def test_ablation_evaluator_execution(self):
        """Validates running RQ2AblationEvaluator across all splits."""
        mock_dataset = {
            "MBPP": [
                DatasetRecord(task_id="m1", dataset="MBPP", prompt="Add", code=self.clean_code, tests=[{"input": [1, 2], "expected_output": 3}], is_hallucinated=False)
            ],
            "CodeHaluEval": [
                DatasetRecord(task_id="c1", dataset="CodeHaluEval", prompt="Add", code=self.dynamic_bug_code, tests=[{"input": [2, 3], "expected_output": 5}], is_hallucinated=True)
            ],
            "HalluCode": [
                DatasetRecord(task_id="h1", dataset="HalluCode", prompt="Sqrt", code=self.static_bug_code, tests=[], is_hallucinated=True)
            ]
        }

        ablation_report = self.evaluator.run_full_ablation(mock_dataset)
        splits = ablation_report["splits"]

        self.assertIn("MBPP", splits)
        self.assertIn("CodeHaluEval", splits)
        self.assertIn("HalluCode", splits)
        self.assertIn("Combined", splits)

        for split_name in ["MBPP", "CodeHaluEval", "HalluCode", "Combined"]:
            for method in ["SDHD-S", "SDHD-D", "SDHD"]:
                self.assertIn(method, splits[split_name])
                m = splits[split_name][method]["metrics"]
                self.assertIn("Precision", m)
                self.assertIn("Recall", m)
                self.assertIn("F1", m)
                self.assertIn("Accuracy", m)
                self.assertIn("FPR", m)

    def test_table4_markdown_generation(self):
        """Validates Table IV Markdown formatting."""
        mock_dataset = {
            "MBPP": [
                DatasetRecord(task_id="m1", dataset="MBPP", prompt="Add", code=self.clean_code, tests=[{"input": [1, 2], "expected_output": 3}], is_hallucinated=False)
            ]
        }
        ablation_report = self.evaluator.run_full_ablation(mock_dataset)
        md_text = self.evaluator.generate_table4_markdown(ablation_report)

        self.assertIn("# Table IV: Ablation Study of SDHD Components", md_text)
        self.assertIn("| Dataset | Method | Precision | Recall | F1 Score | Accuracy | FPR |", md_text)
        self.assertIn("SDHD-S", md_text)
        self.assertIn("SDHD-D", md_text)
        self.assertIn("SDHD", md_text)


if __name__ == "__main__":
    unittest.main()
