"""
test_phase4_aggregation.py - Unit & Integration Tests for Phase 4 (Output Formalization & Aggregation)
====================================================================================================
Validates Section III-D and Section III-E of the SDHD paper:
1. 8-Type Taxonomy Definition & Normalization (DCH, SAH, IH, ESH, PCH, CBH, LDH, LFH)
2. Canonical Record Normalization (source, type_code, error_type, location, variable_name, line_number, detail)
3. Formal Aggregation: D_Output = O1 U O2 with deduplication on (location, content)
4. Full Pipeline JSON Serialization & Schema Integrity on clean and buggy samples
"""

import json
import unittest
from typing import Dict, Any, List

from sdhd_pipeline import (
    SDHD_Pipeline,
    ALL_TAXONOMY_CODES,
    TAXONOMY_MAP,
    TAXONOMY_SOURCES,
    get_type_code,
    normalize_hallucination_record,
    aggregate_and_deduplicate
)


class TestPhase4Aggregation(unittest.TestCase):

    def test_taxonomy_8_types_normalization(self):
        """Validates all 8 taxonomy codes are recognized and mapped to canonical names."""
        self.assertEqual(len(ALL_TAXONOMY_CODES), 8)
        expected_codes = {"DCH", "SAH", "IH", "ESH", "PCH", "CBH", "LDH", "LFH"}
        self.assertEqual(set(ALL_TAXONOMY_CODES), expected_codes)

        for code in ALL_TAXONOMY_CODES:
            self.assertIn(code, TAXONOMY_MAP)
            self.assertIn(code, TAXONOMY_SOURCES)
            self.assertEqual(get_type_code(code), code)
            self.assertEqual(get_type_code(TAXONOMY_MAP[code]), code)

    def test_canonical_record_normalization(self):
        """Validates that arbitrary raw records are properly canonicalized."""
        raw_static = {
            "error_type": "Data Compliance Hallucination (DCH)",
            "variable_name": "x + y",
            "line_number": 12,
            "detail": "Incompatible types int and str."
        }
        norm_static = normalize_hallucination_record(raw_static, default_source="static")
        self.assertEqual(norm_static["source"], "static")
        self.assertEqual(norm_static["type_code"], "DCH")
        self.assertEqual(norm_static["error_type"], "Data Compliance Hallucination (DCH)")
        self.assertEqual(norm_static["location"], "x + y")
        self.assertEqual(norm_static["variable_name"], "x + y")
        self.assertEqual(norm_static["line_number"], 12)
        self.assertEqual(norm_static["detail"], "Incompatible types int and str.")

        raw_dynamic = {
            "type_code": "LDH",
            "location": "test_index_0",
            "detail": "Input: [5] | Expected: 10 | Actual: 6"
        }
        norm_dynamic = normalize_hallucination_record(raw_dynamic, default_source="dynamic")
        self.assertEqual(norm_dynamic["source"], "dynamic")
        self.assertEqual(norm_dynamic["type_code"], "LDH")
        self.assertEqual(norm_dynamic["error_type"], "Logical Deviation Hallucination (LDH)")
        self.assertEqual(norm_dynamic["location"], "test_index_0")
        self.assertEqual(norm_dynamic["variable_name"], "test_index_0")
        self.assertIsNone(norm_dynamic["line_number"])

    def test_lbh_alias_normalization(self):
        """Validates that legacy 'LBH' is normalized to 'LFH' per Table VII."""
        self.assertEqual(get_type_code("LBH"), "LFH")
        self.assertEqual(get_type_code("Logical Boundary Hallucination (LBH)"), "LFH")

    def test_static_dynamic_aggregation_union(self):
        """Validates D_Output = O1 U O2 correctly aggregates static and dynamic findings."""
        o1 = [
            {"type_code": "IH", "location": "var_a", "line_number": 4, "detail": "Undefined var"},
            {"type_code": "DCH", "location": "str + int", "line_number": 8, "detail": "Bad add"}
        ]
        o2 = [
            {"type_code": "LDH", "location": "test_index_1", "line_number": None, "detail": "Mismatch"}
        ]

        d_output = aggregate_and_deduplicate(o1, o2)
        self.assertEqual(len(d_output), 3)
        sources = {rec["source"] for rec in d_output}
        self.assertEqual(sources, {"static", "dynamic"})
        type_codes = {rec["type_code"] for rec in d_output}
        self.assertEqual(type_codes, {"IH", "DCH", "LDH"})

    def test_deduplication_exact_and_cross_iteration(self):
        """Validates that duplicate dynamic detections across refinement iterations are collapsed."""
        o1 = [
            {"type_code": "IH", "location": "x", "line_number": 2, "detail": "Undefined"},
            {"type_code": "IH", "location": "x", "line_number": 2, "detail": "Undefined"}
        ]
        o2 = [
            {"type_code": "LDH", "location": "test_index_0", "line_number": None, "detail": "Actual 5 != 10"},
            {"type_code": "LDH", "location": "test_index_0", "line_number": None, "detail": "Actual 5 != 10"}
        ]

        d_output = aggregate_and_deduplicate(o1, o2)
        self.assertEqual(len(d_output), 2)

    def test_clean_code_full_pipeline_pass(self):
        """Validates full pipeline on clean code produces PASS and zero counts for all 8 categories."""
        clean_code = """
def multiply(a: int, b: int) -> int:
    return a * b
"""
        def mock_generator(reqs, code, feedback, count):
            return [{"input": [i, 2], "expected_output": i * 2} for i in range(10)]

        pipeline = SDHD_Pipeline(c_min=10, i_max=2)
        report = pipeline.run("Multiply two numbers", clean_code, test_gen_fn=mock_generator)

        # Validate JSON serializability
        json_str = json.dumps(report, indent=2)
        self.assertIsInstance(json_str, str)

        summary = report["summary"]
        self.assertEqual(summary["overall_status"], "PASS")
        self.assertEqual(summary["total_hallucinations"], 0)
        self.assertEqual(summary["static_detections"], 0)
        self.assertEqual(summary["dynamic_detections"], 0)
        self.assertEqual(summary["dynamic_status"], "PASS")

        # Check all 8 categories are present and 0
        breakdown = summary["breakdown_by_type"]
        self.assertEqual(len(breakdown), 8)
        for code in ALL_TAXONOMY_CODES:
            self.assertEqual(breakdown[code], 0, f"Category {code} should be 0")

        self.assertEqual(len(report["hallucinations"]), 0)
        self.assertEqual(report["stages"]["static"]["status"], "COMPLETED")
        self.assertEqual(report["stages"]["dynamic"]["status"], "PASS")

    def test_buggy_code_full_pipeline_json_report(self):
        """Validates full pipeline on buggy code produces POTENTIAL_HALLUCINATION and valid JSON."""
        # Code with static bug (unimported module ESH) and dynamic bug (wrong logic)
        buggy_code = """
def calculate_power(base, exp):
    # ESH: math not imported
    return math.pow(base, exp) + 1
"""
        def mock_generator(reqs, code, feedback, count):
            # Tests expecting correct power
            return [{"input": [2, i], "expected_output": 2 ** i} for i in range(10)]

        pipeline = SDHD_Pipeline(c_min=10, i_max=2)
        report = pipeline.run("Calculate power of base to exp", buggy_code, test_gen_fn=mock_generator)

        # Validate JSON serializability
        json_str = json.dumps(report, indent=2)
        self.assertIsInstance(json_str, str)

        summary = report["summary"]
        self.assertEqual(summary["overall_status"], "POTENTIAL_HALLUCINATION")
        self.assertGreater(summary["total_hallucinations"], 0)
        self.assertGreaterEqual(summary["static_detections"], 1)

        # Check 8-type breakdown has exact keys
        breakdown = summary["breakdown_by_type"]
        self.assertEqual(set(breakdown.keys()), set(ALL_TAXONOMY_CODES))
        self.assertGreaterEqual(breakdown["ESH"], 1)

        # Check hallucinations records shape
        for h in report["hallucinations"]:
            self.assertIn("source", h)
            self.assertIn("type_code", h)
            self.assertIn("error_type", h)
            self.assertIn("location", h)
            self.assertIn("line_number", h)
            self.assertIn("detail", h)


if __name__ == "__main__":
    unittest.main()
