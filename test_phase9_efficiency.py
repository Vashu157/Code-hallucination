"""
test_phase9_efficiency.py - Unit & Comparative Tests for Phase 9 (RQ3 Refinement & Efficiency)
==============================================================================================
Validates Section IV-E, Tables V & VI, and Figures 4 & 5 of the SDHD paper:
1. Table V: Iteration-by-iteration refinement impact
2. Table VI: Runtime latency and efficiency profiling (Static vs Dynamic vs Total)
3. Figure 4: C_min coverage sensitivity sweep
4. Figure 5: I_max iteration sensitivity sweep
"""

import unittest
from dataset_loaders import DatasetRecord
from evaluate_rq3 import (
    RQ3RefinementEvaluator,
    RQ3EfficiencyProfiler,
    RQ3SensitivitySweeper,
    run_rq3_pipeline
)


class TestPhase9Efficiency(unittest.TestCase):

    def setUp(self):
        def _mock_gen(reqs, code, feedback, count):
            return [{"input": [1, 2], "expected_output": 3}] * count
        self.mock_gen = _mock_gen

        self.mock_dataset = [
            DatasetRecord(
                task_id="clean1", dataset="MBPP", prompt="Add",
                code="def add(a, b): return a + b",
                tests=[{"input": [1, 2], "expected_output": 3}],
                is_hallucinated=False
            ),
            DatasetRecord(
                task_id="bug1", dataset="CodeHaluEval", prompt="Multiply",
                code="def mul(a, b): return a + b",
                tests=[{"input": [2, 3], "expected_output": 6}],
                is_hallucinated=True
            ),
            DatasetRecord(
                task_id="bug2", dataset="HalluCode", prompt="Undefined",
                code="def undef(): return missing_var + 1",
                tests=[],
                is_hallucinated=True
            )
        ]

    def test_iteration_tracking_table5(self):
        """Validates metric progression across iterations for Table V."""
        evaluator = RQ3RefinementEvaluator(c_min=5, test_gen_fn=self.mock_gen)
        results = evaluator.evaluate_iterations(self.mock_dataset, max_iter=3)

        self.assertEqual(len(results), 3)
        for it in [1, 2, 3]:
            self.assertIn(it, results)
            m = results[it]
            self.assertIn("Precision", m)
            self.assertIn("Recall", m)
            self.assertIn("F1", m)
            self.assertIn("Accuracy", m)

        md_text = evaluator.generate_table5_markdown(results)
        self.assertIn("# Table V: Impact of Refinement Iterations", md_text)
        self.assertIn("Iteration 1", md_text)
        self.assertIn("Iteration 2", md_text)
        self.assertIn("Iteration 3", md_text)

    def test_runtime_profiling_table6(self):
        """Validates execution latency and throughput profiling for Table VI."""
        profiler = RQ3EfficiencyProfiler(c_min=5, i_max=2, test_gen_fn=self.mock_gen)
        dataset_dict = {"TestSplit": self.mock_dataset}
        profile_res = profiler.profile_all(dataset_dict)

        self.assertIn("TestSplit", profile_res)
        self.assertIn("Combined", profile_res)

        for name in ["TestSplit", "Combined"]:
            p = profile_res[name]
            self.assertEqual(p["count"], len(self.mock_dataset))
            self.assertGreaterEqual(p["avg_static_ms"], 0.0)
            self.assertGreaterEqual(p["avg_dynamic_ms"], 0.0)
            self.assertGreaterEqual(p["avg_total_ms"], 0.0)
            self.assertGreaterEqual(p["throughput_tasks_per_sec"], 0.0)

        md_text = profiler.generate_table6_markdown(profile_res)
        self.assertIn("# Table VI: Computational Efficiency & Latency Breakdown", md_text)
        self.assertIn("Avg Static Time", md_text)
        self.assertIn("Avg Dynamic Time", md_text)

    def test_cmin_sensitivity_sweep(self):
        """Validates C_min parameter sweep for Figure 4."""
        sweeper = RQ3SensitivitySweeper(test_gen_fn=self.mock_gen)
        cmin_res = sweeper.sweep_cmin(self.mock_dataset, cmin_values=[5, 10])

        self.assertEqual(len(cmin_res), 2)
        for c in [5, 10]:
            self.assertIn(c, cmin_res)
            self.assertIn("F1", cmin_res[c])

    def test_imax_sensitivity_sweep(self):
        """Validates I_max parameter sweep for Figure 5."""
        sweeper = RQ3SensitivitySweeper(test_gen_fn=self.mock_gen)
        imax_res = sweeper.sweep_imax(self.mock_dataset, imax_values=[1, 2, 3])

        self.assertEqual(len(imax_res), 3)
        for it in [1, 2, 3]:
            self.assertIn(it, imax_res)
            self.assertIn("F1", imax_res[it])

        md_text = sweeper.generate_sensitivity_markdown(
            {5: {"Precision": 1.0, "Recall": 1.0, "F1": 1.0, "Accuracy": 1.0}},
            imax_res
        )
        self.assertIn("# Parameter Sensitivity Analysis", md_text)
        self.assertIn("Figure 4: Sensitivity to Coverage Threshold C_min", md_text)
        self.assertIn("Figure 5: Sensitivity to Maximum Refinement Iterations I_max", md_text)


if __name__ == "__main__":
    unittest.main()
