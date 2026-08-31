"""
test_phase2_static.py - Comprehensive Unit Tests for Phase 2 Static Detection (6 of 6 Types)
=============================================================================================
Taxonomy Tested:
1. DCH (Data Compliance Hallucination)
2. SAH (Structure Access Hallucination)
3. IH  (Identity Hallucination)
4. ESH (External Source Hallucination)
5. PCH (Physical Constraint Hallucination)
6. CBH (Computational Boundary Hallucination)
7. Clean Code Validation (0 False Positives)
"""

import unittest
from static_analysis import detect_hallucinations


class TestPhase2StaticHallucinations(unittest.TestCase):

    # 1. DCH Tests
    def test_dch_incompatible_binary_op(self):
        code = """
def format_user(name, age: int):
    x = age + " years old"
    return x
"""
        errors = detect_hallucinations(code)
        dch_errors = [e for e in errors if e['error_type'] == 'Data Compliance Hallucination (DCH)']
        self.assertGreaterEqual(len(dch_errors), 1, f"Expected DCH for int + str, got: {errors}")

    def test_dch_invalid_method_call(self):
        code = """
def process_data(val):
    x = 42
    x.append(10)
    return x
"""
        errors = detect_hallucinations(code)
        dch_errors = [e for e in errors if e['error_type'] == 'Data Compliance Hallucination (DCH)']
        self.assertGreaterEqual(len(dch_errors), 1, f"Expected DCH for int.append(), got: {errors}")

    # 2. SAH Tests
    def test_sah_dict_missing_key(self):
        code = """
def get_db_port():
    config = {"host": "localhost", "port": 5432}
    return config["database_name"]
"""
        errors = detect_hallucinations(code)
        sah_errors = [e for e in errors if e['error_type'] == 'Structure Access Hallucination (SAH)' and 'dict key' in e['variable_name']]
        self.assertGreaterEqual(len(sah_errors), 1, f"Expected SAH for missing dict key, got: {errors}")

    def test_sah_list_out_of_bounds(self):
        code = """
def get_fifth():
    items = [10, 20, 30]
    return items[5]
"""
        errors = detect_hallucinations(code)
        sah_errors = [e for e in errors if e['error_type'] == 'Structure Access Hallucination (SAH)' and 'out of bounds' in e['variable_name']]
        self.assertGreaterEqual(len(sah_errors), 1, f"Expected SAH for out-of-bounds list index, got: {errors}")

    def test_sah_range_zero_step(self):
        code = """
def iterate():
    for i in range(0, 10, 0):
        pass
"""
        errors = detect_hallucinations(code)
        sah_errors = [e for e in errors if e['error_type'] == 'Structure Access Hallucination (SAH)' and 'range()' in e['variable_name']]
        self.assertGreaterEqual(len(sah_errors), 1, f"Expected SAH for range step 0, got: {errors}")

    # 3. IH Tests
    def test_ih_undefined_var(self):
        code = """
def calculate(a):
    return a + unassigned_value
"""
        errors = detect_hallucinations(code)
        ih_errors = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)']
        self.assertGreaterEqual(len(ih_errors), 1, f"Expected IH for unassigned variable, got: {errors}")

    # 4. ESH Tests
    def test_esh_unimported_call(self):
        code = """
def run_job():
    return phantom_module.execute()
"""
        errors = detect_hallucinations(code)
        esh_errors = [e for e in errors if e['error_type'] == 'External Source Hallucination (ESH)']
        self.assertGreaterEqual(len(esh_errors), 1, f"Expected ESH for phantom module, got: {errors}")

    # 5. PCH Tests
    def test_pch_unbounded_loop_growth(self):
        code = """
def leak_memory():
    data = []
    while True:
        data.append("some_payload")
"""
        errors = detect_hallucinations(code)
        pch_errors = [e for e in errors if e['error_type'] == 'Physical Constraint Hallucination (PCH)']
        self.assertGreaterEqual(len(pch_errors), 1, f"Expected PCH for unbounded collection growth in loop, got: {errors}")

    def test_pch_exponential_growth(self):
        code = """
def blowup():
    s = "init"
    for i in range(100):
        s = s + s
    return s
"""
        errors = detect_hallucinations(code)
        pch_errors = [e for e in errors if e['error_type'] == 'Physical Constraint Hallucination (PCH)']
        self.assertGreaterEqual(len(pch_errors), 1, f"Expected PCH for exponential growth inside loop, got: {errors}")

    # 6. CBH Tests
    def test_cbh_while_true_no_break(self):
        code = """
def spin_forever():
    while True:
        x = 1
"""
        errors = detect_hallucinations(code)
        cbh_errors = [e for e in errors if e['error_type'] == 'Computational Boundary Hallucination (CBH)' and 'while True' in e['variable_name']]
        self.assertGreaterEqual(len(cbh_errors), 1, f"Expected CBH for while True without break, got: {errors}")

    def test_cbh_unmutated_loop_var(self):
        code = """
def infinite_counter(n):
    i = 0
    while i < n:
        print("doing nothing to i")
    return i
"""
        errors = detect_hallucinations(code)
        cbh_errors = [e for e in errors if e['error_type'] == 'Computational Boundary Hallucination (CBH)' and 'loop condition' in e['variable_name']]
        self.assertGreaterEqual(len(cbh_errors), 1, f"Expected CBH for unmutated loop variable, got: {errors}")

    def test_cbh_unbounded_recursion(self):
        code = """
def recurse(n):
    return recurse(n - 1)
"""
        errors = detect_hallucinations(code)
        cbh_errors = [e for e in errors if e['error_type'] == 'Computational Boundary Hallucination (CBH)' and 'recursive function' in e['variable_name']]
        self.assertGreaterEqual(len(cbh_errors), 1, f"Expected CBH for recursion with no base case, got: {errors}")

    # 7. Clean Code Tests (No False Positives)
    def test_clean_code_all_valid_constructs(self):
        code = """
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def count_up(target):
    s = 0
    i = 0
    while i < target:
        s += i
        i += 1
    return s

def access_dict():
    d = {"status": "ok", "code": 200}
    return d["status"]
"""
        errors = detect_hallucinations(code)
        self.assertEqual(len(errors), 0, f"Clean code should produce 0 hallucination errors, got: {errors}")


if __name__ == "__main__":
    unittest.main()
