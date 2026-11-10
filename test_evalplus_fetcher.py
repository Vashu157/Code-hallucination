"""
test_evalplus_fetcher.py - Test Suite for EvalPlus Fetcher & Evaluator
======================================================================
Tests:
1. Release URL resolution and model alias mapping.
2. Windows platform compatibility patches.
3. Sample download, extraction, and directory discovery.
4. Ground truth evaluation against base and plus test suites.
5. Canonical DatasetRecord schema conversion and validation.
6. Serialization / deserialization roundtrip.
7. dataset_loaders.load_evalplus integration and filtering.
"""

import os
import tempfile
import unittest
from dataset_loaders import DatasetRecord, load_evalplus
from evalplus_fetcher import (
    EVALPLUS_MODELS,
    apply_windows_patches,
    convert_to_dataset_record,
    evaluate_single_sample,
    fetch_and_evaluate_evalplus,
    fetch_evalplus_samples,
    get_model_download_url,
    get_or_compute_task_groundtruth,
    load_dataset_records_from_file,
    save_dataset_records,
)


class TestEvalPlusFetcher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        apply_windows_patches()

    def test_get_model_download_url(self):
        """Verifies release URLs for standard models and aliases."""
        he_chatgpt = get_model_download_url("humaneval", "chatgpt")
        self.assertIn("v0.1.0", he_chatgpt)
        self.assertIn("chatgpt_temp_0.0.zip", he_chatgpt)

        he_starcoder = get_model_download_url("HumanEval", "STARCODER")
        self.assertIn("v0.1.0", he_starcoder)
        self.assertIn("starcoder_temp_0.0.zip", he_starcoder)

        mb_gpt35 = get_model_download_url("mbpp", "gpt-3.5-turbo")
        self.assertIn("v0.2.0", mb_gpt35)
        self.assertIn("gpt-3.5-turbo_temp_0.0.zip", mb_gpt35)

        mb_gpt4 = get_model_download_url("MBPP", "gpt-4")
        self.assertIn("v0.2.0", mb_gpt4)
        self.assertIn("gpt-4-1106-preview_temp_0.0.zip", mb_gpt4)

        # Invalid cases
        with self.assertRaises(ValueError):
            get_model_download_url("unknown_dataset", "chatgpt")

        with self.assertRaises(ValueError):
            get_model_download_url("humaneval", "nonexistent_model_xyz")

    def test_windows_patches(self):
        """Verifies Windows compatibility environment variable and time_limit monkeypatch."""
        apply_windows_patches()
        self.assertEqual(os.environ.get("EVALPLUS_MAX_MEMORY_BYTES"), "-1")
        import evalplus.eval.utils as eu
        # Check that calling time_limit as a context manager does not raise AttributeError
        with eu.time_limit(10.0):
            pass

    def test_fetch_evalplus_samples_download_extract(self):
        """Verifies sample downloading, unzipping, and task directory discovery."""
        samples_dir = fetch_evalplus_samples(dataset="humaneval", model="chatgpt")
        self.assertTrue(os.path.isdir(samples_dir))

        # Check that task directories exist with 0.py
        entries = os.listdir(samples_dir)
        task_dirs = [e for e in entries if os.path.isdir(os.path.join(samples_dir, e))]
        self.assertGreater(len(task_dirs), 100)

        # Sample task check
        sample_task_dir = os.path.join(samples_dir, task_dirs[0])
        self.assertTrue(os.path.exists(os.path.join(sample_task_dir, "0.py")))

    def test_evaluate_single_sample_clean(self):
        """Verifies that an oracle canonical solution evaluates to clean (is_hallucinated=False)."""
        from evalplus.data import get_human_eval_plus
        problems = get_human_eval_plus()
        p0 = problems["HumanEval/0"]
        canonical = p0["prompt"] + p0["canonical_solution"]

        res = evaluate_single_sample(
            problem=p0,
            solution_code=canonical,
            dataset="humaneval",
            base_only=False,
            fast_check=True
        )

        self.assertEqual(res["base_status"], "pass")
        self.assertEqual(res["plus_status"], "pass")
        self.assertFalse(res["is_hallucinated"])

    def test_evaluate_single_sample_hallucinated(self):
        """Verifies that a deliberately buggy solution evaluates to hallucinated (is_hallucinated=True)."""
        from evalplus.data import get_human_eval_plus
        problems = get_human_eval_plus()
        p0 = problems["HumanEval/0"]
        # Intentionally wrong code that always returns opposite / fails
        buggy_code = p0["prompt"] + "\n    return False\n"

        res = evaluate_single_sample(
            problem=p0,
            solution_code=buggy_code,
            dataset="humaneval",
            base_only=False,
            fast_check=True
        )

        self.assertEqual(res["base_status"], "fail")
        self.assertTrue(res["is_hallucinated"])

    def test_convert_to_dataset_record_schema(self):
        """Verifies conversion of evaluated sample into a valid DatasetRecord."""
        from evalplus.data import get_human_eval_plus
        problems = get_human_eval_plus()
        p0 = problems["HumanEval/0"]
        oracle = get_or_compute_task_groundtruth(p0, "humaneval")

        eval_res_clean = {
            "base_status": "pass",
            "plus_status": "pass",
            "base_details": [True, True],
            "plus_details": [True, True, True],
            "is_hallucinated": False,
        }

        rec = convert_to_dataset_record(
            problem=p0,
            raw_code="# raw code",
            sanitized_code="def has_close_elements(): pass",
            eval_result=eval_res_clean,
            dataset="humaneval",
            model_name="chatgpt",
            oracle=oracle
        )

        self.assertIsInstance(rec, DatasetRecord)
        self.assertEqual(rec.task_id, "EvalPlus/HumanEval/0")
        self.assertEqual(rec.dataset, "EvalPlus-HumanEval")
        self.assertFalse(rec.is_hallucinated)
        self.assertEqual(rec.ground_truth_labels, [])
        self.assertEqual(rec.metadata["model"], "chatgpt")
        self.assertEqual(rec.metadata["base_status"], "pass")
        self.assertEqual(rec.metadata["plus_status"], "pass")
        self.assertGreater(len(rec.tests), 0)

        # Test hallucinated record conversion with LDH
        eval_res_ldh = {
            "base_status": "pass",
            "plus_status": "fail",
            "base_details": [True, True],
            "plus_details": [True, False],
            "is_hallucinated": True,
        }
        rec_ldh = convert_to_dataset_record(
            problem=p0,
            raw_code="# raw",
            sanitized_code="def code(): pass",
            eval_result=eval_res_ldh,
            dataset="humaneval",
            model_name="chatgpt",
            oracle=oracle
        )
        self.assertTrue(rec_ldh.is_hallucinated)
        self.assertEqual(rec_ldh.ground_truth_labels[0]["type_code"], "LDH")

    def test_serialization_roundtrip(self):
        """Verifies save_dataset_records and load_dataset_records_from_file."""
        rec = DatasetRecord(
            task_id="EvalPlus/HumanEval/999",
            dataset="EvalPlus-HumanEval",
            prompt="def dummy(): pass",
            code="def dummy(): return 42",
            clean_code="def dummy(): return 42",
            tests=[{"assertion": "assert dummy() == 42"}],
            ground_truth_labels=[{"type_code": "LDH", "error_type": "Logical Deviation"}],
            is_hallucinated=True,
            metadata={"model": "test_model"}
        )

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            save_dataset_records([rec], temp_path)
            loaded = load_dataset_records_from_file(temp_path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].task_id, rec.task_id)
            self.assertEqual(loaded[0].dataset, rec.dataset)
            self.assertEqual(loaded[0].code, rec.code)
            self.assertEqual(loaded[0].is_hallucinated, rec.is_hallucinated)
            self.assertEqual(loaded[0].metadata["model"], "test_model")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_load_evalplus_loader_integration(self):
        """Verifies dataset_loaders.load_evalplus with filtering and record structure."""
        # Use existing saved records from previous evaluation run
        records = load_evalplus(dataset="humaneval", model="chatgpt", n=5)
        self.assertEqual(len(records), 5)
        for r in records:
            self.assertIsInstance(r, DatasetRecord)
            self.assertTrue(r.dataset.startswith("EvalPlus"))
            self.assertIn("base_status", r.metadata)

        # Clean only
        clean_records = load_evalplus(dataset="humaneval", model="chatgpt", clean_only=True)
        for r in clean_records:
            self.assertFalse(r.is_hallucinated)

        # Hallucinated only
        hallu_records = load_evalplus(dataset="humaneval", model="chatgpt", hallucinated_only=True)
        for r in hallu_records:
            self.assertTrue(r.is_hallucinated)


if __name__ == "__main__":
    unittest.main()
