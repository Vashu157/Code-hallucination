"""
test_phase6_baselines.py - Unit & Comparative Tests for Phase 6 (Baseline Reproduction)
========================================================================================
Validates Section IV-C1 and Table III of the SDHD paper:
1. PyLint Baseline (Traditional static analysis linter)
2. Flake8 Baseline (Traditional static style and error linter)
3. CodeEval Baseline (Pure dynamic test execution)
4. CodeHalu Baseline (Tian et al. [17])
5. SelfDebug Baseline (Chen et al. [6])
6. SelfCheck Baseline (Li et al. [22])
7. SAC3 Baseline (Manakul et al. [23])
8. SDHD Adapter (Uniform interface wrapper)
9. run_all_baselines_on_record runner (Definition of Done)
10. Evaluation Metrics Harness (Precision, Recall, F1, Accuracy, FPR)
"""

import unittest
from baselines import (
    BaseBaseline,
    PyLintBaseline,
    Flake8Baseline,
    CodeEvalBaseline,
    CodeHaluBaseline,
    SelfDebugBaseline,
    SelfCheckBaseline,
    SAC3Baseline,
    SDHDBaselineAdapter,
    run_all_baselines_on_record,
    calculate_metrics,
    evaluate_detector,
    evaluate_all_baselines
)
from dataset_loaders import DatasetRecord, load_all_datasets


class TestPhase6Baselines(unittest.TestCase):

    def test_pylint_baseline(self):
        """Validates PyLint static analysis baseline and error code mapping."""
        pylint = PyLintBaseline()

        # Clean code -> no errors
        clean_code = "def add(a, b):\n    return a + b\n"
        res_clean = pylint.detect("Add two numbers", clean_code)
        self.assertEqual(res_clean["method"], "PyLint")
        self.assertFalse(res_clean["is_hallucinated"])
        self.assertEqual(len(res_clean["detections"]), 0)

        # Buggy code with undefined variable -> IH mapped from E0602
        buggy_code = "def calc(x):\n    return x + ghost_var\n"
        res_buggy = pylint.detect("Add to x", buggy_code)
        self.assertTrue(res_buggy["is_hallucinated"])
        self.assertGreaterEqual(len(res_buggy["detections"]), 1)
        self.assertTrue(any(d["error_type"] == "Identity Hallucination (IH)" for d in res_buggy["detections"]))

    def test_flake8_baseline(self):
        """Validates Flake8 static linter baseline and error code mapping."""
        flake8 = Flake8Baseline()

        # Clean code
        clean_code = "def mult(a, b):\n    return a * b\n"
        res_clean = flake8.detect("Multiply two numbers", clean_code)
        self.assertEqual(res_clean["method"], "Flake8")
        self.assertFalse(res_clean["is_hallucinated"])
        self.assertEqual(len(res_clean["detections"]), 0)

        # Buggy code with undefined variable -> IH mapped from F821
        buggy_code = "def mult(a, b):\n    return a * ghost_factor\n"
        res_buggy = flake8.detect("Multiply", buggy_code)
        self.assertTrue(res_buggy["is_hallucinated"])
        self.assertGreaterEqual(len(res_buggy["detections"]), 1)
        self.assertTrue(any(d["error_type"] == "Identity Hallucination (IH)" for d in res_buggy["detections"]))

    def test_code_eval_baseline(self):
        """Validates pure dynamic test execution baseline without static analysis."""
        detector = CodeEvalBaseline(timeout=5)

        # Passing tests
        clean_code = "def add(a, b): return a + b"
        passing_tests = [{"input": [2, 3], "expected_output": 5}]
        res_pass = detector.detect("Add", clean_code, tests=passing_tests)
        self.assertEqual(res_pass["method"], "CodeEval")
        self.assertFalse(res_pass["is_hallucinated"])

        # Failing tests -> LDH
        failing_tests = [{"input": [2, 3], "expected_output": 999}]
        res_fail = detector.detect("Add", clean_code, tests=failing_tests)
        self.assertTrue(res_fail["is_hallucinated"])
        self.assertTrue(any(d["error_type"] == "Logical Deviation Hallucination (LDH)" for d in res_fail["detections"]))

        # Crashing tests -> LFH
        crashing_code = "def div(a, b): return a / b"
        crashing_tests = [{"input": [1, 0], "expected_output": 0}]
        res_crash = detector.detect("Divide", crashing_code, tests=crashing_tests)
        self.assertTrue(res_crash["is_hallucinated"])
        self.assertTrue(any(d["error_type"] == "Logical Failure Hallucination (LFH)" for d in res_crash["detections"]))

    def test_self_debug_baseline(self):
        """Validates Self-Debug LLM prompting baseline."""
        def mock_llm_response(prompt, code):
            if "buggy" in code:
                return {
                    "is_hallucinated": True,
                    "confidence": 0.95,
                    "method": "SelfDebug",
                    "detections": [{
                        "error_type": "Identity Hallucination (IH)",
                        "variable_name": "ghost_val",
                        "line_number": 2,
                        "detail": "ghost_val is undefined."
                    }],
                    "details": {"explanation": "Found undefined variable"}
                }
            return {
                "is_hallucinated": False,
                "confidence": 0.05,
                "method": "SelfDebug",
                "detections": [],
                "details": {"explanation": "No issues found"}
            }

        detector = SelfDebugBaseline(mock_fn=mock_llm_response)
        res_clean = detector.detect("prompt", "def ok(): return 1")
        self.assertFalse(res_clean["is_hallucinated"])

        res_buggy = detector.detect("prompt", "def buggy(): return ghost_val")
        self.assertTrue(res_buggy["is_hallucinated"])
        self.assertEqual(res_buggy["detections"][0]["error_type"], "Identity Hallucination (IH)")

    def test_codehalu_detection(self):
        """Validates CodeHalu dynamic execution baseline behavior."""
        detector = CodeHaluBaseline()
        clean_code = "def add(a, b): return a + b"
        clean_tests = [{"input": [2, 3], "expected_output": 5}]
        res_clean = detector.detect("Add two numbers", clean_code, tests=clean_tests)
        self.assertEqual(res_clean["method"], "CodeHalu")
        self.assertFalse(res_clean["is_hallucinated"])

        buggy_code = "def add(a, b): return a * b"
        failing_tests = [{"input": [2, 3], "expected_output": 5}]
        res_buggy = detector.detect("Add two numbers", buggy_code, tests=failing_tests)
        self.assertTrue(res_buggy["is_hallucinated"])

    def test_selfcheck_detection(self):
        """Validates SelfCheck sample-consistency baseline behavior."""
        detector = SelfCheckBaseline(threshold=0.6)
        code = "def double(x): return x * 2"
        consistent_samples = [
            "def double(n): return n * 2",
            "def double(val): return val + val"
        ]
        res_cons = detector.detect("Double the input", code, sample_completions=consistent_samples)
        self.assertEqual(res_cons["method"], "SelfCheck")
        self.assertFalse(res_cons["is_hallucinated"])

        divergent_samples = [
            "import os\ndef execute(): os.system('shutdown')",
            "class DatabaseManager: pass"
        ]
        res_div = detector.detect("Double the input", code, sample_completions=divergent_samples)
        self.assertTrue(res_div["is_hallucinated"])

    def test_sac3_detection(self):
        """Validates SAC3 semantic similarity baseline behavior."""
        detector = SAC3Baseline(threshold=0.3)
        matching_prompt = "Calculate circle area given radius using math pi"
        matching_code = "import math\ndef circle_area(radius): return math.pi * radius * radius"
        res_match = detector.detect(matching_prompt, matching_code)
        self.assertEqual(res_match["method"], "SAC3")
        self.assertFalse(res_match["is_hallucinated"])

        unrelated_prompt = "Calculate circle area given radius"
        unrelated_code = "def fetch_database_users(): return []"
        res_unrelated = detector.detect(unrelated_prompt, unrelated_code)
        self.assertTrue(res_unrelated["is_hallucinated"])

    def test_run_all_baselines_on_record(self):
        """Definition of Done: Runner executes all comparison baselines side-by-side."""
        record = {
            "task_id": 101,
            "prompt": "Add two numbers",
            "code": "def add(a, b):\n    return a + ghost_var\n",
            "tests": [{"input": [2, 3], "expected_output": 5}]
        }

        def mock_self_debug(p, c):
            return {"is_hallucinated": True, "confidence": 1.0, "method": "SelfDebug", "detections": [], "details": {}}

        results = run_all_baselines_on_record(record, self_debug_mock_fn=mock_self_debug)

        expected_methods = ["SDHD", "PyLint", "Flake8", "CodeEval", "CodeHalu", "SelfDebug", "SelfCheck", "SAC3"]
        for m in expected_methods:
            self.assertIn(m, results, f"Method {m} must be present in side-by-side run")
            self.assertIn("is_hallucinated", results[m])
            self.assertIn("confidence", results[m])
            self.assertIn("detections", results[m])
            self.assertIn("details", results[m])

        # PyLint, Flake8, and CodeEval should all catch the ghost_var bug
        self.assertTrue(results["PyLint"]["is_hallucinated"])
        self.assertTrue(results["Flake8"]["is_hallucinated"])
        self.assertTrue(results["CodeEval"]["is_hallucinated"])

    def test_metrics_calculation(self):
        """Validates mathematical correctness of Precision, Recall, F1, Accuracy, and FPR."""
        y_true = [True,  True,  False, False]
        y_pred = [True,  False, True,  False]
        metrics = calculate_metrics(y_true, y_pred)
        self.assertEqual(metrics["TP"], 1)
        self.assertEqual(metrics["FN"], 1)
        self.assertEqual(metrics["FP"], 1)
        self.assertEqual(metrics["TN"], 1)
        self.assertEqual(metrics["Precision"], 0.5)
        self.assertEqual(metrics["Recall"], 0.5)
        self.assertEqual(metrics["F1"], 0.5)
        self.assertEqual(metrics["Accuracy"], 0.5)
        self.assertEqual(metrics["FPR"], 0.5)


if __name__ == "__main__":
    unittest.main()
