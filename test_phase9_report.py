"""
test_phase9_report.py - Test Suite for Phase 9 Report Generation
================================================================
Verifies that generate_report.py correctly constructs the comprehensive,
publication-grade final report SDHD_Final_Report.md with all required chapters,
mathematical formulations, empirical tables (RQ1-RQ5), threats to validity,
and source code appendices.
"""

import os
import unittest
import tempfile
from generate_report import generate_report


class TestPhase9Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate to a temporary location to test clean invocation
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.test_report_path = os.path.join(cls.temp_dir.name, "Test_Report.md")
        cls.report_content = generate_report(cls.test_report_path)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_01_report_file_creation_and_size(self):
        """Test that the final report file is created and has substantial content (>50KB)."""
        self.assertTrue(os.path.exists(self.test_report_path))
        file_size = os.path.getsize(self.test_report_path)
        self.assertGreater(file_size, 50000, f"Report file size {file_size} is suspiciously small.")
        self.assertGreater(len(self.report_content), 50000)

    def test_02_all_chapters_present(self):
        """Test that all 7 mandatory chapters are present in the report."""
        required_chapters = [
            "CHAPTER 1: INTRODUCTION & PROBLEM STATEMENT",
            "CHAPTER 2: LITERATURE REVIEW & BASELINE PARADIGMS",
            "CHAPTER 3: SDHD SYSTEM ARCHITECTURE & METHODOLOGY",
            "CHAPTER 4: IMPLEMENTATION & CODEBASE ORGANIZATION",
            "CHAPTER 5: EMPIRICAL EVALUATION & EXPERIMENTAL RESULTS",
            "CHAPTER 6: DEVIATIONS FROM BASE PAPER & THREATS TO VALIDITY",
            "CHAPTER 7: CONCLUSION & FUTURE DIRECTIONS"
        ]
        for chapter in required_chapters:
            with self.subTest(chapter=chapter):
                self.assertIn(chapter, self.report_content, f"Missing chapter: {chapter}")

    def test_03_all_empirical_tables_present(self):
        """Test that all empirical comparison tables (Table 1.1 through 6.1) are present."""
        required_tables = [
            "Table 1.1: Standardized 8-Type Hallucination Taxonomy",
            "Table 2.1: Overview of Evaluated Detection Paradigms",
            "Table 5.1: Hallucination Detection Performance Across Datasets (RQ1 Reproduction)",
            "Table 5.2: Ablation Study of SDHD Components (RQ2 Reproduction)",
            "Table 5.3: Test-Suite Size Sensitivity & Coverage Gate Analysis (RQ3 Reproduction)",
            "Table 5.4: Static Program Representation Comparison (RQ4 Reproduction)",
            "Table 5.5: Category Breakdown Matrix Across 8 Types (RQ5 Reproduction)",
            "Table 6.1: Methodological Deviations from Base Paper"
        ]
        for table in required_tables:
            with self.subTest(table=table):
                self.assertIn(table, self.report_content, f"Missing table: {table}")

    def test_04_mathematical_formulations_present(self):
        """Test that key mathematical algorithms and formulas are properly documented."""
        formulas = [
            "DF(d)",  # Dominance frontier
            "O_1",    # Static stage output
            "O_2",    # Dynamic stage output
            "D_{Output} = O_1 \\cup O_2",  # Normalization / aggregation
            "C_{min}", # Coverage threshold
            "I_{max}"  # Maximum iterations
        ]
        for formula in formulas:
            with self.subTest(formula=formula):
                self.assertIn(formula, self.report_content, f"Missing mathematical formula component: {formula}")

    def test_05_chapter_6_threats_to_validity(self):
        """Test that Chapter 6 explicitly covers LLM substitution, benchmark differences, and validity threats."""
        required_sections = [
            "6.1 LLM Substitution Analysis (Gemini vs GPT-3.5)",
            "6.2 Benchmark Scale & Dataset Scope Differences",
            "6.3 Threats to Internal, External, and Construct Validity"
        ]
        for sec in required_sections:
            with self.subTest(section=sec):
                self.assertIn(sec, self.report_content, f"Missing Chapter 6 subsection: {sec}")

    def test_06_appendix_codebase_integrity(self):
        """Test that Appendix I contains full source code for all 8 system modules."""
        expected_modules = [
            "static_analysis.py",
            "test_case_generator.py",
            "dynamic_executor.py",
            "sdhd_pipeline.py",
            "dataset_loaders.py",
            "baselines.py",
            "evaluate_rq1.py",
            "ablation.py"
        ]
        self.assertIn("## APPENDIX I: COMPLETE SOURCE CODE REPOSITORY", self.report_content)
        for mod in expected_modules:
            with self.subTest(module=mod):
                marker = f"### File: {mod}"
                self.assertIn(marker, self.report_content, f"Appendix missing code for module {mod}")

    def test_07_workspace_default_report_generation(self):
        """Test that default invocation generates SDHD_Final_Report.md in the workspace."""
        workspace_report = "SDHD_Final_Report.md"
        self.assertTrue(os.path.exists(workspace_report))
        self.assertGreater(os.path.getsize(workspace_report), 100000)


if __name__ == "__main__":
    unittest.main()
