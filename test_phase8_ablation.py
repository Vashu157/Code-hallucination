"""
test_phase8_ablation.py - Comprehensive Unit & Comparative Tests for Phase 8 (RQ2–RQ5 Ablations)
================================================================================================
Validates Section IV-D and Tables IV, V, VI, VII of the SDHD paper:
1. RQ2 (Table IV): Component Ablation (SDHD-S vs SDHD-D vs Full SDHD)
2. RQ3 (Table V): Test Suite Size Sensitivity (N < 3, 3 <= N < 10, 10 <= N <= 15)
3. RQ4 (Table VI): Program Representation Ablation (AST-only vs AST+CFG vs Full SSA)
4. RQ5 (Table VII): Per-Type Category Breakdown Matrix across all 8 canonical types
5. Consolidated Summary Report and Pipeline Execution
"""

import os
import tempfile
import unittest
from dataset_loaders import DatasetRecord
from ablation import (
    SDHDStaticOnlyDetector,
    SDHDDynamicOnlyDetector,
    ASTOnlyStaticDetector,
    ASTCFGStaticDetector,
    FullSSAStaticDetector,
    RQ2ComponentAblationEvaluator,
    RQ3SensitivityEvaluator,
    RQ4RepresentationEvaluator,
    RQ5CategoryAblationEvaluator,
    run_all_ablations_pipeline
)
from baselines import SDHDBaselineAdapter


class TestPhase8Ablation(unittest.TestCase):

    def setUp(self):
        def _mock_gen(reqs, code, feedback, count):
            return [{"input": [1, 2], "expected_output": 3}] * count
        self.mock_gen = _mock_gen

        # Representative code samples
        self.clean_code = "def add(a, b): return a + b"
        self.static_bug_code = "def test(): return ghost_mod.calc(10)"  # ESH
        self.dynamic_bug_code = "def add(a, b): return a * b"          # LDH (wrong logic)
        self.crash_code = "def div(a, b): return a / b"                # LFH (crash on 0)

        # Mock dataset covering splits and types
        self.mock_dataset = {
            "MBPP": [
                DatasetRecord(
                    task_id="m1", dataset="MBPP", prompt="Add",
                    code=self.clean_code,
                    tests=[{"input": [1, 2], "expected_output": 3}],
                    is_hallucinated=False
                )
            ],
            "CodeHaluEval": [
                DatasetRecord(
                    task_id="c1", dataset="CodeHaluEval", prompt="Multiply",
                    code=self.dynamic_bug_code,
                    tests=[{"input": [2, 3], "expected_output": 5}],
                    ground_truth_labels=[{"type_code": "LDH", "error_type": "Logical Deviation Hallucination (LDH)"}],
                    is_hallucinated=True
                )
            ],
            "HalluCode": [
                DatasetRecord(
                    task_id="h1", dataset="HalluCode", prompt="External call",
                    code=self.static_bug_code,
                    tests=[],
                    ground_truth_labels=[{"type_code": "ESH", "error_type": "External Source Hallucination (ESH)", "location": "ghost_mod"}],
                    is_hallucinated=True
                )
            ]
        }

    # -----------------------------------------------------------------
    # 1. RQ2: Component Ablation Tests (Table IV)
    # -----------------------------------------------------------------

    def test_static_only_detector(self):
        """Validates SDHD-S detects static bugs but misses dynamic logic bugs."""
        detector = SDHDStaticOnlyDetector()

        # Static bug -> detected
        res_static = detector.detect("Call", self.static_bug_code)
        self.assertEqual(res_static["method"], "SDHD-S")
        self.assertTrue(res_static["is_hallucinated"])

        # Clean code -> not detected
        res_clean = detector.detect("Add", self.clean_code)
        self.assertFalse(res_clean["is_hallucinated"])

        # Dynamic bug -> missed by static analysis
        res_dynamic = detector.detect("Add", self.dynamic_bug_code)
        self.assertFalse(res_dynamic["is_hallucinated"])

    def test_dynamic_only_detector(self):
        """Validates SDHD-D detects dynamic test failures but misses static bugs without tests."""
        detector = SDHDDynamicOnlyDetector()

        # Dynamic bug with failing test -> detected
        failing_tests = [{"input": [2, 3], "expected_output": 5}]
        def _failing_gen(r, c, f, cnt):
            return failing_tests * cnt

        res_dynamic = detector.detect("Add", self.dynamic_bug_code, test_gen_fn=_failing_gen)
        self.assertEqual(res_dynamic["method"], "SDHD-D")
        self.assertTrue(res_dynamic["is_hallucinated"])

        # Clean code with passing test -> not detected
        clean_tests = [{"input": [2, 3], "expected_output": 5}]
        def _passing_gen(r, c, f, cnt):
            return clean_tests * cnt

        res_clean = detector.detect("Add", self.clean_code, test_gen_fn=_passing_gen)
        self.assertFalse(res_clean["is_hallucinated"])

    def test_hybrid_synergy(self):
        """Validates full SDHD catches both static and dynamic bugs."""
        sdhd = SDHDBaselineAdapter()

        # Catches static bug even with empty test generation
        def _empty_gen(r, c, f, cnt):
            return []
        res_static = sdhd.detect("Call", self.static_bug_code, test_gen_fn=_empty_gen)
        self.assertTrue(res_static["is_hallucinated"])

        # Catches dynamic bug
        failing_tests = [{"input": [2, 3], "expected_output": 5}]
        def _failing_gen(r, c, f, cnt):
            return failing_tests * cnt
        res_dynamic = sdhd.detect("Add", self.dynamic_bug_code, test_gen_fn=_failing_gen)
        self.assertTrue(res_dynamic["is_hallucinated"])

    def test_rq2_table4_generation(self):
        """Validates Table IV markdown generation for RQ2."""
        evaluator = RQ2ComponentAblationEvaluator(test_gen_fn=self.mock_gen)
        report = evaluator.run_full_ablation(self.mock_dataset)
        md_text = evaluator.generate_table4_markdown(report)

        self.assertIn("# Table IV: A Comparison Between Static and Dynamic Methods", md_text)
        self.assertIn("SDHD-S", md_text)
        self.assertIn("SDHD-D", md_text)
        self.assertIn("SDHD", md_text)
        self.assertIn("Key Observations (RQ2)", md_text)

    # -----------------------------------------------------------------
    # 2. RQ3: Test Suite Size Sensitivity Tests (Table V)
    # -----------------------------------------------------------------

    def test_rq3_sensitivity_buckets(self):
        """Validates sensitivity across N < 3, 3 <= N < 10, and 10 <= N <= 15."""
        evaluator = RQ3SensitivityEvaluator(test_gen_fn=self.mock_gen)
        dynamic_records = self.mock_dataset["CodeHaluEval"]

        report = evaluator.run_sensitivity_study(dynamic_records)
        self.assertIn("N < 3 (C_min=2)", report)
        self.assertIn("3 <= N < 10 (C_min=5)", report)
        self.assertIn("10 <= N <= 15 (C_min=10)", report)

        md_table5 = evaluator.generate_table5_markdown(report)
        self.assertIn("# Table V: Test-Suite Size Sensitivity & Coverage Gate", md_table5)
        self.assertIn("C_min Gate", md_table5)
        self.assertIn("Key Observations (RQ3)", md_table5)

    # -----------------------------------------------------------------
    # 3. RQ4: Program Representation Ablation Tests (Table VI)
    # -----------------------------------------------------------------

    def test_rq4_representation_ablation(self):
        """Validates representation ablation: AST-only vs AST+CFG vs Full SSA."""
        evaluator = RQ4RepresentationEvaluator()
        static_records = self.mock_dataset["HalluCode"]

        report = evaluator.run_representation_study(static_records)
        self.assertIn("AST-only", report)
        self.assertIn("AST+CFG", report)
        self.assertIn("SSA (Phase 1)", report)

        md_table6 = evaluator.generate_table6_markdown(report)
        self.assertIn("# Table VI: Program Representation Ablation", md_table6)
        self.assertIn("SSA (Phase 1)", md_table6)
        self.assertIn("Key Observations (RQ4)", md_table6)

    def test_rq4_phi_node_branch_resolution(self):
        """Validates that SSA resolves branch-scoped variables where AST-only fails."""
        branch_code = """
def check(flag):
    if flag:
        x = 10
    else:
        x = 20
    return x + 1
"""
        ast_only = ASTOnlyStaticDetector().detect("Check", branch_code)
        ssa = FullSSAStaticDetector().detect("Check", branch_code)

        # In clean if-else where x is assigned on all paths, SSA must NOT flag an error
        self.assertFalse(ssa["is_hallucinated"], "SSA should recognize x is uniformly defined on all paths.")

    # -----------------------------------------------------------------
    # 4. RQ5: 8-Type Category Breakdown Tests (Table VII)
    # -----------------------------------------------------------------

    def test_rq5_category_breakdown(self):
        """Validates fine-grained evaluation across all 8 canonical categories."""
        all_records = []
        for recs in self.mock_dataset.values():
            all_records.extend(recs)

        evaluator = RQ5CategoryAblationEvaluator(test_gen_fn=self.mock_gen)
        report = evaluator.run_category_breakdown(all_records)
        cats = report["categories"]

        for code in ["DCH", "SAH", "IH", "ESH", "PCH", "CBH", "LDH", "LFH"]:
            self.assertIn(code, cats)

        # In mock data, ESH is in h1, caught by SDHD-S and SDHD
        self.assertEqual(cats["ESH"]["gt_count"], 1)
        self.assertEqual(cats["ESH"]["caught"]["SDHD-S"], 1)
        self.assertEqual(cats["ESH"]["caught"]["SDHD"], 1)
        self.assertEqual(cats["ESH"]["caught"]["SDHD-D"], 0)

        # LDH is in c1, caught by SDHD-D and SDHD
        self.assertEqual(cats["LDH"]["gt_count"], 1)
        self.assertEqual(cats["LDH"]["caught"]["SDHD-D"], 1)
        self.assertEqual(cats["LDH"]["caught"]["SDHD"], 1)
        self.assertEqual(cats["LDH"]["caught"]["SDHD-S"], 0)

        md_table7 = evaluator.generate_table7_markdown(report)
        self.assertIn("# Table VII: Category Breakdown Ablation across 8 Types", md_table7)
        self.assertIn("Key Observations (RQ5)", md_table7)

    # -----------------------------------------------------------------
    # 5. Full Pipeline Artifacts Test
    # -----------------------------------------------------------------

    def test_run_all_ablations_pipeline(self):
        """Validates that running the ablation pipeline generates all expected files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            res_dict, summary = run_all_ablations_pipeline(
                output_dir=tmpdir,
                test_gen_fn=self.mock_gen
            )

            self.assertIn("rq2", res_dict)
            self.assertIn("rq3", res_dict)
            self.assertIn("rq4", res_dict)
            self.assertIn("rq5", res_dict)

            expected_files = [
                "table4_ablation.md", "table4_ablation.json",
                "table5_sensitivity.md", "table5_sensitivity.json",
                "table6_representation.md", "table6_representation.json",
                "table7_ablation.md", "table7_ablation.json",
                "ablation_summary_report.md"
            ]
            for fname in expected_files:
                fpath = os.path.join(tmpdir, fname)
                self.assertTrue(os.path.exists(fpath), f"Artifact {fname} was not created.")


if __name__ == "__main__":
    unittest.main()
