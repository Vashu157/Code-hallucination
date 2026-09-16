"""
test_phase10_cross_file.py — Unit & Integration Tests for Phase 10 (Cross-File & Multi-Module)
==============================================================================================
"""

import os
import sys
import unittest
import tempfile
import subprocess
from typing import Dict, Any

from cross_file_analyzer import (
    ProjectSymbolTable,
    CrossFileStaticDetector,
    MultiFileSDHDRunner
)


class TestPhase10CrossFile(unittest.TestCase):
    """Test suite validating cross-file symbol resolution, multi-file runner, and CLI."""

    def setUp(self):
        self.project_files = {
            "math_utils.py": """
def add(a: int, b: int) -> int:
    return a + b

def subtract(a: int, b: int) -> int:
    return a - b

PI = 3.14159
""",
            "geometry/shapes.py": """
from math_utils import PI

class Circle:
    def __init__(self, radius: float):
        self.radius = radius

    def area(self) -> float:
        return PI * (self.radius ** 2)
""",
            "main.py": """
from math_utils import add, subtract, PI
from geometry.shapes import Circle

def compute():
    total = add(10, 20)
    diff = subtract(20, 5)
    c = Circle(5.0)
    return total, diff, c.area()
"""
        }

    def test_symbol_table_extraction(self):
        """Validates that ProjectSymbolTable accurately extracts exports across modules."""
        table = ProjectSymbolTable.from_files(self.project_files)

        self.assertIn("math_utils", table.modules)
        self.assertIn("geometry.shapes", table.modules)
        self.assertIn("main", table.modules)

        math_syms = table.get_module("math_utils")
        self.assertIn("add", math_syms.functions)
        self.assertIn("subtract", math_syms.functions)
        self.assertIn("PI", math_syms.variables)

        geo_syms = table.get_module("geometry.shapes")
        self.assertIn("Circle", geo_syms.classes)
        self.assertIn("area", geo_syms.classes["Circle"])

    def test_cross_file_valid_imports_no_esh(self):
        """Validates that valid cross-module imports do NOT trigger ESH false positives."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        main_code = self.project_files["main.py"]
        errors = detector.analyze_source(main_code, current_module="main", file_path="main.py")

        # There should be 0 hallucinations in clean cross-file imports
        self.assertEqual(len(errors), 0, f"Expected 0 errors, got: {errors}")

    def test_cross_file_missing_symbol_triggers_esh(self):
        """Validates that importing a non-existent symbol from a local module triggers ESH."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        buggy_code = """
from math_utils import add, non_existent_function

def compute():
    return add(1, 2)
"""
        errors = detector.analyze_source(buggy_code, current_module="main", file_path="main.py")

        esh_errors = [e for e in errors if e.get("type_code") == "ESH"]
        self.assertGreater(len(esh_errors), 0)
        self.assertTrue(any("non_existent_function" in e.get("variable_name", "") for e in esh_errors))

    def test_cross_file_attribute_call_missing_method(self):
        """Validates that calling a non-existent attribute on an imported module triggers ESH."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        buggy_code = """
import math_utils

def compute():
    return math_utils.calculate_tensor(10)
"""
        errors = detector.analyze_source(buggy_code, current_module="main", file_path="main.py")

        esh_errors = [e for e in errors if e.get("type_code") == "ESH"]
        self.assertGreater(len(esh_errors), 0)
        self.assertTrue(any("calculate_tensor" in e.get("variable_name", "") for e in esh_errors))

    def test_multi_file_sdhd_runner(self):
        """Validates MultiFileSDHDRunner analyzing an entire multi-file project repository."""
        runner = MultiFileSDHDRunner(files_dict=self.project_files)
        report = runner.analyze_project()

        self.assertEqual(report["files_analyzed"], 3)
        self.assertEqual(report["overall_status"], "PASS")
        self.assertEqual(report["total_hallucinations"], 0)

        # Now introduce a bug in one file
        buggy_files = dict(self.project_files)
        buggy_files["broken.py"] = """
def bad():
    return x + undefined_symbol
"""
        runner_buggy = MultiFileSDHDRunner(files_dict=buggy_files)
        report_buggy = runner_buggy.analyze_project()

        self.assertEqual(report_buggy["files_analyzed"], 4)
        self.assertEqual(report_buggy["overall_status"], "POTENTIAL_HALLUCINATION")
        self.assertGreater(report_buggy["total_hallucinations"], 0)
        self.assertEqual(report_buggy["file_reports"]["broken.py"]["status"], "POTENTIAL_HALLUCINATION")

    def test_cli_execution_clean_code(self):
        """Validates that cli.py runs cleanly via subprocess on clean code."""
        cmd = [
            sys.executable,
            "cli.py",
            "--code", "def add(a, b): return a + b",
            "--prompt", "Add two numbers",
            "--static-only"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Status: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
