"""
test_phase5_datasets.py - Unit & Integration Tests for Phase 5 (Dataset Integration)
=====================================================================================
Validates Section IV-A and Table II of the SDHD paper:
1. Unified DatasetRecord Contract (task_id, dataset, prompt, code, tests, ground_truth_labels, is_hallucinated)
2. MBPP Loader as Clean-Code Pool (for FPR testing)
3. CodeHaluEval Loader (dynamic tests, LDH/LFH annotations)
4. HalluCode Loader (static annotations across DCH, SAH, IH, ESH, PCH, CBH)
5. Dataset Summary Generation (Table II shape)
6. Pipeline Execution directly on DatasetRecord instances
"""

import unittest
from dataset_loaders import (
    DatasetRecord,
    load_mbpp,
    load_codehalueval,
    load_hallucode,
    load_all_datasets,
    get_dataset_summary
)
from sdhd_pipeline import SDHD_Pipeline


class TestPhase5Datasets(unittest.TestCase):

    def test_dataset_record_schema(self):
        """Validates DatasetRecord schema properties and serialization."""
        rec = DatasetRecord(
            task_id="test_01",
            dataset="CodeHaluEval",
            prompt="Compute something",
            code="def f(x): return x",
            clean_code="def f(x): return x",
            tests=[{"input": [1], "expected_output": 1}],
            ground_truth_labels=[{"type_code": "LDH", "error_type": "Logical Deviation Hallucination (LDH)"}],
            is_hallucinated=True,
            metadata={"difficulty": "easy"}
        )
        d = rec.to_dict()
        self.assertEqual(d["task_id"], "test_01")
        self.assertEqual(d["dataset"], "CodeHaluEval")
        self.assertEqual(d["prompt"], "Compute something")
        self.assertEqual(d["code"], "def f(x): return x")
        self.assertEqual(len(d["tests"]), 1)
        self.assertEqual(len(d["ground_truth_labels"]), 1)
        self.assertTrue(d["is_hallucinated"])
        self.assertEqual(d["metadata"]["difficulty"], "easy")

    def test_load_mbpp_clean_pool(self):
        """Validates MBPP loader produces clean-code pool with is_hallucinated=False."""
        mbpp_records = load_mbpp(n=5, clean_only=True)
        self.assertGreaterEqual(len(mbpp_records), 1)

        for rec in mbpp_records:
            self.assertEqual(rec.dataset, "MBPP")
            self.assertFalse(rec.is_hallucinated, "MBPP clean pool tasks must have is_hallucinated=False")
            self.assertIsNotNone(rec.prompt)
            self.assertGreater(len(rec.prompt), 0)
            self.assertIsNotNone(rec.code)
            self.assertGreater(len(rec.code), 0)
            self.assertEqual(len(rec.ground_truth_labels), 0)

    def test_load_codehalueval_dynamic_tests(self):
        """Validates CodeHaluEval loader loads tasks with dynamic test suites and ground-truth labels."""
        codehalu_records = load_codehalueval(n=5)
        self.assertGreaterEqual(len(codehalu_records), 1)

        has_labeled_task = False
        for rec in codehalu_records:
            self.assertEqual(rec.dataset, "CodeHaluEval")
            self.assertIsNotNone(rec.prompt)
            self.assertIsNotNone(rec.code)
            self.assertGreaterEqual(len(rec.tests), 1, "CodeHaluEval records must include executable test cases")
            if rec.is_hallucinated:
                self.assertGreaterEqual(len(rec.ground_truth_labels), 1)
                has_labeled_task = True

        self.assertTrue(has_labeled_task, "Should contain labeled hallucination tasks")

    def test_load_hallucode_static_labels(self):
        """Validates HalluCode loader loads tasks covering static hallucination types with Test=N/A."""
        hallucode_records = load_hallucode(n=7)
        self.assertGreaterEqual(len(hallucode_records), 1)

        observed_types = set()
        for rec in hallucode_records:
            self.assertEqual(rec.dataset, "HalluCode")
            self.assertEqual(len(rec.tests), 0, "HalluCode has Test = N/A per Table II")
            for label in rec.ground_truth_labels:
                observed_types.add(label.get("type_code"))

        # Verify coverage of static categories in sample pool
        expected_static_samples = {"DCH", "SAH", "IH", "ESH", "PCH", "CBH"}
        self.assertTrue(observed_types.intersection(expected_static_samples), "Should cover static hallucination types")

    def test_load_all_datasets_and_summary(self):
        """Validates unified load_all_datasets and Table II summary generation."""
        all_data = load_all_datasets()
        self.assertIn("MBPP", all_data)
        self.assertIn("CodeHaluEval", all_data)
        self.assertIn("HalluCode", all_data)

        summary = get_dataset_summary(all_data)
        self.assertIn("MBPP", summary)
        self.assertIn("CodeHaluEval", summary)
        self.assertIn("HalluCode", summary)

        # Validate summary fields for each benchmark
        for name in ["MBPP", "CodeHaluEval", "HalluCode"]:
            s = summary[name]
            self.assertIn("total_tasks", s)
            self.assertIn("clean_tasks", s)
            self.assertIn("hallucinated_tasks", s)
            self.assertIn("total_test_cases", s)
            self.assertIn("avg_tests_per_task", s)
            self.assertIn("annotated_type_breakdown", s)

        # Check HalluCode test count is 0 per Table II
        self.assertEqual(summary["HalluCode"]["total_test_cases"], 0)
        self.assertEqual(summary["HalluCode"]["avg_tests_per_task"], 0.0)

    def test_pipeline_compatibility_with_dataset_records(self):
        """Validates SDHD_Pipeline runs seamlessly on DatasetRecord instances across all 3 datasets."""
        pipeline = SDHD_Pipeline(c_min=5, i_max=2)

        # 1. Clean MBPP task -> expected PASS
        clean_mbpp = load_mbpp(n=1, clean_only=True)[0]
        def mock_mbpp_gen(r, c, f, count):
            return clean_mbpp.tests
        mbpp_report = pipeline.run(clean_mbpp.prompt, clean_mbpp.code, test_gen_fn=mock_mbpp_gen)
        self.assertEqual(mbpp_report["summary"]["overall_status"], "PASS")

        # 2. Labeled CodeHaluEval task (e.g. LDH) -> expected POTENTIAL_HALLUCINATION
        codehalu_tasks = load_codehalueval(n=2)
        hallu_task = [t for t in codehalu_tasks if t.is_hallucinated][0]
        def mock_codehalu_gen(r, c, f, count):
            return hallu_task.tests
        codehalu_report = pipeline.run(hallu_task.prompt, hallu_task.code, test_gen_fn=mock_codehalu_gen)
        self.assertEqual(codehalu_report["summary"]["overall_status"], "POTENTIAL_HALLUCINATION")

        # 3. Labeled HalluCode task (e.g. ESH or DCH) -> expected static detection
        hallucode_tasks = load_hallucode(n=4)
        hallu_static_task = [t for t in hallucode_tasks if t.is_hallucinated][0]
        hallucode_report = pipeline.run(hallu_static_task.prompt, hallu_static_task.code, test_gen_fn=lambda r,c,f,cnt: [])
        self.assertGreater(hallucode_report["summary"]["static_detections"], 0)


if __name__ == "__main__":
    unittest.main()
