"""
test_phase6_baselines.py - Unit & Comparative Tests for Phase 6 (Baseline Reproduction)
========================================================================================
Validates Section IV-C1 and Table III of the SDHD paper:
1. CodeHalu Baseline (Execution-based dynamic verification)
2. SelfCheck Baseline (Sample-consistency agreement)
3. SAC3 Baseline (Semantic similarity / cosine distance)
4. SDHD Adapter (Uniform interface wrapper)
5. Evaluation Metrics Harness (Precision, Recall, F1, Accuracy, FPR)
6. Comparative Multi-Baseline Evaluation Run
"""

import unittest
from baselines import (
    BaseBaseline,
    CodeHaluBaseline,
    SelfCheckBaseline,
    SAC3Baseline,
    SDHDBaselineAdapter,
    calculate_metrics,
    evaluate_detector,
    evaluate_all_baselines
)
from dataset_loaders import DatasetRecord, load_all_datasets


class TestPhase6Baselines(unittest.TestCase):

    def test_codehalu_detection(self):
        """Validates CodeHalu dynamic execution baseline behavior."""
        detector = CodeHaluBaseline()

        # Clean code + passing test -> not hallucinated
        clean_code = "def add(a, b): return a + b"
        clean_tests = [{"input": [2, 3], "expected_output": 5}]
        res_clean = detector.detect("Add two numbers", clean_code, tests=clean_tests)
        self.assertEqual(res_clean["method"], "CodeHalu")
        self.assertFalse(res_clean["is_hallucinated"])

        # Buggy code + failing test -> is_hallucinated
        buggy_code = "def add(a, b): return a * b"
        failing_tests = [{"input": [2, 3], "expected_output": 5}]
        res_buggy = detector.detect("Add two numbers", buggy_code, tests=failing_tests)
        self.assertTrue(res_buggy["is_hallucinated"])

    def test_selfcheck_detection(self):
        """Validates SelfCheck sample-consistency baseline behavior."""
        detector = SelfCheckBaseline(threshold=0.6)

        # Consistent completions
        code = "def double(x): return x * 2"
        consistent_samples = [
            "def double(n): return n * 2",
            "def double(val): return val + val"
        ]
        res_cons = detector.detect("Double the input", code, sample_completions=consistent_samples)
        self.assertEqual(res_cons["method"], "SelfCheck")
        self.assertFalse(res_cons["is_hallucinated"])

        # Highly divergent completion -> low agreement
        divergent_samples = [
            "import os\ndef execute(): os.system('shutdown')",
            "class DatabaseManager: pass"
        ]
        res_div = detector.detect("Double the input", code, sample_completions=divergent_samples)
        self.assertTrue(res_div["is_hallucinated"])

    def test_sac3_detection(self):
        """Validates SAC3 semantic similarity baseline behavior."""
        detector = SAC3Baseline(threshold=0.3)

        # Highly matching prompt and code
        matching_prompt = "Calculate circle area given radius using math pi"
        matching_code = "import math\ndef circle_area(radius): return math.pi * radius * radius"
        res_match = detector.detect(matching_prompt, matching_code)
        self.assertEqual(res_match["method"], "SAC3")
        self.assertFalse(res_match["is_hallucinated"])

        # Completely unrelated code -> low semantic similarity
        unrelated_prompt = "Calculate circle area given radius"
        unrelated_code = "def fetch_database_users(): return []"
        res_unrelated = detector.detect(unrelated_prompt, unrelated_code)
        self.assertTrue(res_unrelated["is_hallucinated"])

    def test_sdhd_adapter(self):
        """Validates SDHDBaselineAdapter outputs uniform baseline schema."""
        adapter = SDHDBaselineAdapter()
        clean_code = "def add(a, b): return a + b"
        def mock_gen(r, c, f, count):
            return [{"input": [i, 1], "expected_output": i + 1} for i in range(10)]

        res = adapter.detect("Add two numbers", clean_code, test_gen_fn=mock_gen)
        self.assertEqual(res["method"], "SDHD")
        self.assertIn("is_hallucinated", res)
        self.assertIn("confidence", res)
        self.assertIn("details", res)
        self.assertFalse(res["is_hallucinated"])

    def test_metrics_calculation(self):
        """Validates mathematical correctness of Precision, Recall, F1, Accuracy, and FPR."""
        # 3 TP, 1 FP, 1 FN, 5 TN (Total = 10)
        y_true = [True, True, True, True, False, False, False, False, False, False]
        y_pred = [True, True, True, False, True, False, False, False, False, False]

        m = calculate_metrics(y_true, y_pred)
        self.assertEqual(m["TP"], 3)
        self.assertEqual(m["FP"], 1)
        self.assertEqual(m["FN"], 1)
        self.assertEqual(m["TN"], 5)
        self.assertEqual(m["total"], 10)

        # Precision = 3 / (3 + 1) = 0.75
        self.assertEqual(m["Precision"], 0.75)
        # Recall = 3 / (3 + 1) = 0.75
        self.assertEqual(m["Recall"], 0.75)
        # F1 = 2 * 0.75 * 0.75 / (1.5) = 0.75
        self.assertEqual(m["F1"], 0.75)
        # Accuracy = (3 + 5) / 10 = 0.8
        self.assertEqual(m["Accuracy"], 0.8)
        # FPR = FP / (FP + TN) = 1 / (1 + 5) = 0.1667
        self.assertEqual(m["FPR"], 0.1667)

    def test_multi_baseline_comparative_run(self):
        """Validates running all 4 baselines on a benchmark dataset."""
        dataset = [
            DatasetRecord(
                task_id="clean_1",
                dataset="MBPP",
                prompt="Add two numbers",
                code="def add(a, b): return a + b",
                tests=[{"input": [2, 3], "expected_output": 5}],
                is_hallucinated=False
            ),
            DatasetRecord(
                task_id="buggy_1",
                dataset="CodeHaluEval",
                prompt="Add two numbers",
                code="def add(a, b): return a * b",
                tests=[{"input": [2, 3], "expected_output": 5}],
                is_hallucinated=True
            ),
        ]

        results = evaluate_all_baselines(dataset)
        self.assertIn("SDHD", results)
        self.assertIn("CodeHalu", results)
        self.assertIn("SelfCheck", results)
        self.assertIn("SAC3", results)

        for name in ["SDHD", "CodeHalu", "SelfCheck", "SAC3"]:
            m = results[name]
            self.assertIn("Precision", m)
            self.assertIn("Recall", m)
            self.assertIn("F1", m)
            self.assertIn("Accuracy", m)
            self.assertIn("FPR", m)


if __name__ == "__main__":
    unittest.main()
