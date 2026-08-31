"""
test_phase3_dynamic.py - Comprehensive Unit Tests for Phase 3 Dynamic Pipeline (Algorithm 3)
============================================================================================
Validates:
1. Requirement Analysis (Structured schema extraction)
2. Coverage Gate (C_min threshold enforcement)
3. Iterative Refinement Feedback Loop (incorporating feedback over up to I_max iterations)
4. Early Termination on PASS
5. Loop Exhaustion returning POTENTIAL_HALLUCINATION
"""

import unittest
from test_case_generator import (
    extract_requirements,
    generate_feedback
)
from sdhd_pipeline import SDHD_Pipeline


class TestPhase3DynamicPipeline(unittest.TestCase):

    def test_requirement_extraction_structured(self):
        prompt = "Compute the area of a circle given radius r. Raise ValueError if r < 0."
        code = """
import math
def circle_area(r):
    if r < 0:
        raise ValueError("radius cannot be negative")
    return math.pi * r * r
"""
        reqs = extract_requirements(prompt, code)
        self.assertIn("function_name", reqs)
        self.assertEqual(reqs["function_name"], "circle_area")
        self.assertIn("parameters", reqs)
        self.assertIn("r", reqs["parameters"])

    def test_coverage_gate_triggers_refinement(self):
        """Tests that when coverage < C_min, the pipeline generates feedback and continues."""
        calls = []

        def mock_generator(reqs, code, feedback, count):
            calls.append(feedback)
            if len(calls) == 1:
                # First iteration: deliberately return insufficient tests (3 < 10)
                return [{"input": [1], "expected_output": 1}] * 3
            else:
                # Second iteration: return sufficient tests (10)
                return [{"input": [i], "expected_output": i * 2} for i in range(10)]

        code = """
def double_val(x):
    return x * 2
"""
        pipeline = SDHD_Pipeline(c_min=10, i_max=3)
        res = pipeline.run("Double the input integer", code, test_gen_fn=mock_generator)

        # Assert that it took 2 iterations and second call had coverage feedback
        self.assertEqual(res["summary"]["refinement_iterations"], 2)
        self.assertIsNotNone(calls[1], "Second call should receive feedback from first shortfall")
        self.assertIn("Coverage shortfall", calls[1])
        self.assertEqual(res["summary"]["overall_status"], "PASS")

    def test_refinement_loop_convergence_after_failure(self):
        """Tests that execution failures generate feedback and lead to PASS on next iteration."""
        calls = []

        def mock_generator(reqs, code, feedback, count):
            calls.append(feedback)
            if len(calls) == 1:
                # First iteration: flawed test case expectation causing LDH
                tests = [{"input": [i], "expected_output": i * 2} for i in range(9)]
                tests.append({"input": [10], "expected_output": 999})  # Flawed expectation
                return tests
            else:
                # Second iteration (with feedback): all correct expectations
                return [{"input": [i], "expected_output": i * 2} for i in range(10)]

        code = """
def double_val(x):
    return x * 2
"""
        pipeline = SDHD_Pipeline(c_min=10, i_max=3)
        res = pipeline.run("Double the input integer", code, test_gen_fn=mock_generator)

        self.assertEqual(res["summary"]["refinement_iterations"], 2)
        self.assertIsNotNone(calls[1])
        self.assertIn("Logical Deviation", calls[1])
        self.assertEqual(res["summary"]["overall_status"], "PASS")

    def test_loop_exhaustion_potential_hallucination(self):
        """Tests that code with a persistent logical bug exhausts I_max and flags POTENTIAL_HALLUCINATION."""
        calls = []

        def mock_generator(reqs, code, feedback, count):
            calls.append(feedback)
            # Consistently tests correct requirements
            return [{"input": [i], "expected_output": i * 2} for i in range(10)]

        # Flawed code (adds 1 instead of doubling)
        buggy_code = """
def double_val(x):
    return x + 1
"""
        pipeline = SDHD_Pipeline(c_min=10, i_max=3)
        res = pipeline.run("Double the input integer", buggy_code, test_gen_fn=mock_generator)

        self.assertEqual(res["summary"]["refinement_iterations"], 3)
        self.assertEqual(res["summary"]["overall_status"], "POTENTIAL_HALLUCINATION")
        self.assertEqual(res["summary"]["dynamic_status"], "POTENTIAL_HALLUCINATION")
        self.assertGreater(res["summary"]["dynamic_detections"], 0)

    def test_clean_code_immediate_pass(self):
        """Tests that correct code with valid tests passes on iteration 1."""
        def mock_generator(reqs, code, feedback, count):
            return [{"input": [i], "expected_output": i * 2} for i in range(10)]

        code = """
def double_val(x):
    return x * 2
"""
        pipeline = SDHD_Pipeline(c_min=10, i_max=3)
        res = pipeline.run("Double the input integer", code, test_gen_fn=mock_generator)

        self.assertEqual(res["summary"]["refinement_iterations"], 1)
        self.assertEqual(res["summary"]["overall_status"], "PASS")
        self.assertEqual(res["summary"]["total_hallucinations"], 0)


if __name__ == "__main__":
    unittest.main()
