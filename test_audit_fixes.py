import unittest
from static_analysis import detect_hallucinations

class TestPhase0To2AuditFixes(unittest.TestCase):

    def test_comprehension_undefined_ih(self):
        code = '''
def foo():
    return [ghost_item for i in range(10)]
'''
        errors = detect_hallucinations(code)
        ih = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)' and e['variable_name'] == 'ghost_item']
        self.assertEqual(len(ih), 1)

    def test_lambda_undefined_ih(self):
        code = '''
def foo():
    f = lambda x: ghost_var + x
    return f(2)
'''
        errors = detect_hallucinations(code)
        ih = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)' and e['variable_name'] == 'ghost_var']
        self.assertEqual(len(ih), 1)

    def test_ternary_undefined_ih(self):
        code = '''
def foo(c):
    return ghost_a if c else 1
'''
        errors = detect_hallucinations(code)
        ih = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)' and e['variable_name'] == 'ghost_a']
        self.assertEqual(len(ih), 1)

    def test_class_method_undefined_ih(self):
        code = '''
class Solution:
    def solve(self, x):
        return x + ghost_member
'''
        errors = detect_hallucinations(code)
        ih = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)' and e['variable_name'] == 'ghost_member']
        self.assertEqual(len(ih), 1)

    def test_module_level_const_clean(self):
        code = '''
BASE_CONFIG = 100
def get_config():
    return BASE_CONFIG
'''
        errors = detect_hallucinations(code)
        self.assertEqual(len(errors), 0, f"Expected 0 errors on clean module constant access, got: {errors}")

    def test_class_instantiation_clean(self):
        code = '''
class Greeter:
    def greet(self):
        return 'hi'

def make_greeter():
    return Greeter()
'''
        errors = detect_hallucinations(code)
        self.assertEqual(len(errors), 0, f"Expected 0 errors on local class instantiation, got: {errors}")

    def test_call_non_callable_int_dch(self):
        code = '''
def foo():
    x = 42
    return x(10)
'''
        errors = detect_hallucinations(code)
        dch = [e for e in errors if e['error_type'] == 'Data Compliance Hallucination (DCH)' and 'x()' in e['variable_name']]
        self.assertEqual(len(dch), 1)

    def test_string_out_of_bounds_sah(self):
        code = '''
def foo():
    s = "hello"
    return s[10]
'''
        errors = detect_hallucinations(code)
        sah = [e for e in errors if e['error_type'] == 'Structure Access Hallucination (SAH)' and 'index 10' in e['variable_name']]
        self.assertEqual(len(sah), 1)

    def test_slice_zero_step_sah(self):
        code = '''
def foo(s):
    return s[::0]
'''
        errors = detect_hallucinations(code)
        sah = [e for e in errors if e['error_type'] == 'Structure Access Hallucination (SAH)' and 'slice step 0' in e['variable_name']]
        self.assertEqual(len(sah), 1)

if __name__ == '__main__':
    unittest.main()
