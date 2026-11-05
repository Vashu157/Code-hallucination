"""
test_phase10_cross_file.py — Unit & Integration Tests for Phase 10 (Cross-File & Multi-Module)
==============================================================================================
Validates Section VI-C of Yang et al. (IEEE TSE 2026):
1. Multi-module symbol extraction and deferred dependency resolution.
2. Cross-file import validation (ESH detection and false positive elimination).
3. Cross-file class inheritance, MRO resolution, and instance method access (SAH).
4. Cross-file function call arity and signature enforcement (DCH).
5. Aliased imports and transitive re-exports across package __init__.py.
6. Circular import resilience.
7. MultiFileSDHDRunner project-wide orchestration.
8. Production CLI execution via subprocess.
"""

import os
import sys
import unittest
import tempfile
import subprocess
import json
from typing import Dict, Any

from cross_file_analyzer import (
    ProjectSymbolTable,
    CrossFileStaticDetector,
    MultiFileSDHDRunner,
    FunctionSignature,
    ClassDefInfo
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

class Shape:
    def __init__(self, color: str = "blue"):
        self.color = color

    def get_color(self) -> str:
        return self.color

class Circle(Shape):
    def __init__(self, radius: float):
        super().__init__("red")
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

        # Verify signature extraction
        add_sig = math_syms.functions["add"]
        self.assertEqual(add_sig.min_args, 2)
        self.assertEqual(add_sig.max_args, 2)
        self.assertEqual(add_sig.param_names, ["a", "b"])

        geo_syms = table.get_module("geometry.shapes")
        self.assertIn("Circle", geo_syms.classes)
        self.assertIn("area", geo_syms.classes["Circle"])
        self.assertIn("Shape", geo_syms.classes)

    def test_cross_file_valid_imports_no_esh(self):
        """Validates that valid cross-module imports do NOT trigger ESH false positives."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        main_code = self.project_files["main.py"]
        errors = detector.analyze_source(main_code, current_module="main", file_path="main.py")

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

    def test_cross_file_aliased_module_import(self):
        """Validates aliased imports (import x as y) for both valid and hallucinated calls."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        clean_code = """
import math_utils as mu

def compute():
    return mu.add(10, 20)
"""
        errors_clean = detector.analyze_source(clean_code, current_module="main", file_path="main.py")
        self.assertEqual(len(errors_clean), 0, f"Expected 0 errors for valid alias call, got: {errors_clean}")

        hallu_code = """
import math_utils as mu

def compute():
    return mu.fake_matrix_op(10)
"""
        errors_hallu = detector.analyze_source(hallu_code, current_module="main", file_path="main.py")
        esh = [e for e in errors_hallu if e.get("type_code") == "ESH"]
        self.assertGreater(len(esh), 0)
        self.assertTrue(any("fake_matrix_op" in e.get("variable_name", "") for e in esh))

    def test_cross_file_class_inheritance(self):
        """Validates that cross-file class inheritance resolves inherited methods without false SAH."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        # Calling get_color() on Circle should pass because Circle inherits from Shape!
        code = """
from geometry.shapes import Circle

def test_shape():
    c = Circle(5.0)
    col = c.get_color()
    a = c.area()
    return col, a
"""
        errors = detector.analyze_source(code, current_module="main", file_path="main.py")
        self.assertEqual(len(errors), 0, f"Inherited method call should have 0 errors, got: {errors}")

    def test_cross_file_instance_attribute_sah(self):
        """Validates that calling a nonexistent method on a cross-file class instance triggers SAH."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        buggy_code = """
from geometry.shapes import Circle

def test_shape():
    c = Circle(5.0)
    return c.non_existent_method()
"""
        errors = detector.analyze_source(buggy_code, current_module="main", file_path="main.py")
        sah_errors = [e for e in errors if e.get("type_code") == "SAH"]
        self.assertGreater(len(sah_errors), 0)
        self.assertTrue(any("non_existent_method" in e.get("variable_name", "") for e in sah_errors))

    def test_cross_file_function_arity_dch(self):
        """Validates that calling a cross-file function with wrong parameter count triggers DCH."""
        table = ProjectSymbolTable.from_files(self.project_files)
        detector = CrossFileStaticDetector(table)

        # add(a, b) expects 2 arguments, calling with 1 should trigger DCH
        buggy_code_too_few = """
from math_utils import add

def run():
    return add(10)
"""
        errors1 = detector.analyze_source(buggy_code_too_few, current_module="main", file_path="main.py")
        dch_errors1 = [e for e in errors1 if e.get("type_code") == "DCH"]
        self.assertGreater(len(dch_errors1), 0)
        self.assertTrue(any("requires at least 2" in e.get("detail", "") for e in dch_errors1))

        # add(a, b) expects 2 arguments, calling with 3 should trigger DCH
        buggy_code_too_many = """
import math_utils

def run():
    return math_utils.add(1, 2, 3)
"""
        errors2 = detector.analyze_source(buggy_code_too_many, current_module="main", file_path="main.py")
        dch_errors2 = [e for e in errors2 if e.get("type_code") == "DCH"]
        self.assertGreater(len(dch_errors2), 0)
        self.assertTrue(any("accepts at most 2" in e.get("detail", "") for e in dch_errors2))

    def test_cross_file_transitive_reexport(self):
        """Validates that package __init__.py re-exporting symbols resolves cleanly across files."""
        pkg_files = {
            "pkg/core.py": """
def worker(task_name: str) -> str:
    return f"Done: {task_name}"
""",
            "pkg/__init__.py": """
from .core import worker

__all__ = ["worker"]
""",
            "client.py": """
from pkg import worker

def do_work():
    return worker("job_1")
"""
        }
        table = ProjectSymbolTable.from_files(pkg_files)
        detector = CrossFileStaticDetector(table)

        client_code = pkg_files["client.py"]
        errors = detector.analyze_source(client_code, current_module="client", file_path="client.py")
        self.assertEqual(len(errors), 0, f"Transitive re-export should have 0 errors, got: {errors}")

    def test_cross_file_circular_import(self):
        """Validates that circular imports between peer modules do not crash with RecursionError."""
        circular_files = {
            "mod_a.py": """
from mod_b import get_b

def get_a() -> str:
    return "a"
""",
            "mod_b.py": """
from mod_a import get_a

def get_b() -> str:
    return "b"
"""
        }
        # Building table and resolving dependencies must terminate without recursion error
        table = ProjectSymbolTable.from_files(circular_files)
        self.assertIn("mod_a", table.modules)
        self.assertIn("mod_b", table.modules)
        self.assertIn("get_a", table.modules["mod_a"].functions)
        self.assertIn("get_b", table.modules["mod_b"].functions)

    def test_multi_file_sdhd_runner(self):
        """Validates MultiFileSDHDRunner analyzing an entire multi-file project repository."""
        runner = MultiFileSDHDRunner(files_dict=self.project_files)
        report = runner.analyze_project()

        self.assertEqual(report["files_analyzed"], 3)
        self.assertEqual(report["overall_status"], "PASS")
        self.assertEqual(report["total_hallucinations"], 0)

        # Introduce a bug in one file
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

    def test_cli_project_dir_execution(self):
        """Validates cli.py executing on a multi-file project directory via subprocess."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = os.path.join(tmpdir, "helper.py")
            with open(file1, "w", encoding="utf-8") as f:
                f.write("def calc(x: int) -> int:\n    return x * 2\n")

            file2 = os.path.join(tmpdir, "main.py")
            with open(file2, "w", encoding="utf-8") as f:
                f.write("from helper import calc\ndef run():\n    return calc(10)\n")

            json_out = os.path.join(tmpdir, "report.json")
            cmd = [
                sys.executable,
                "cli.py",
                "--project-dir", tmpdir,
                "--output-json", json_out
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, f"CLI stderr: {proc.stderr}")

            self.assertTrue(os.path.exists(json_out))
            with open(json_out, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.assertEqual(data["files_analyzed"], 2)
            self.assertEqual(data["overall_status"], "PASS")
            self.assertEqual(data["total_hallucinations"], 0)


if __name__ == "__main__":
    unittest.main()
