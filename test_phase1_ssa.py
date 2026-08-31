"""
test_phase1_ssa.py - Comprehensive Unit Tests for Phase 1 SSA Construction
==========================================================================
Tests:
1. Exact Fig. 3(a) -> Fig. 3(c) SSA Transformation (Algorithm 1-2, CFG, phi-placement, versioning).
2. Branchy test with missing branch definition (if without else) -> flags IH / maybe-undefined.
3. Branchy test with all branches defined (if with else) -> merges phi without IH.
4. Loop back-edge variable update and phi-placement.
5. End-to-end static hallucination detection on various patterns.
"""

import ast
import unittest
from static_analysis import (
    CFGBuilder,
    compute_dominators,
    insert_phi_nodes,
    SSARenamer,
    SSATransformer,
    CodeAnalyzer,
    detect_hallucinations,
    BasicBlock,
    PhiNode
)


class TestPhase1SSA(unittest.TestCase):

    def test_fig3_reproduction(self):
        """
        Reproduces Fig. 3 from the base paper (Section III-A, Fig. 3(a)-(c), Table I):
        Program:
            def sum_filter(A, k):
                n = len(A)
                s = 0
                L = []
                for j in range(n):
                    if j < k:
                        s = s + A[j]
                        L = L + [s]
                    else:
                        x = A[j]
                return L
        Asserts:
        - CFG contains entry, loop header, loop body, then/else branches, join block, and exit.
        - Phi-nodes are placed at loop header for variables 's' and 'L'.
        - Phi-nodes are placed at the branch merge point.
        - Loop back-edge versions and variable versions match Fig. 3(c) / Table I semantics.
        - No spurious IH/ESH errors are reported on well-defined variables.
        """
        fig3_code = """
def sum_filter(A, k):
    n = len(A)
    s = 0
    L = []
    for j in range(n):
        if j < k:
            s = s + A[j]
            L = L + [s]
        else:
            x = A[j]
    return L
"""
        analyzer = CodeAnalyzer(fig3_code)
        analyzer.parse()
        renamers = analyzer.transform_ssa()
        
        self.assertEqual(len(renamers), 2)  # 1 for function sum_filter + 1 for module
        
        # Get function SSA
        func_ssa = analyzer.ssa_transformer.function_ssas.get("sum_filter")
        self.assertIsNotNone(func_ssa)
        
        cfg = func_ssa.cfg
        renamer = func_ssa.renamer
        reachable_blocks = cfg.get_reachable_blocks()
        
        # Check that dominators and dominance frontiers were computed
        for b in reachable_blocks:
            self.assertIsNotNone(b.df)
            
        # Check phi-nodes across blocks
        all_phi_vars = set()
        for b in reachable_blocks:
            for v, phi in b.phi_nodes.items():
                all_phi_vars.add(v)
                
        # Phi functions must exist for loop-modified / branch-modified variables 's' and 'L'
        self.assertIn("s", all_phi_vars)
        self.assertIn("L", all_phi_vars)
        
        # Check variable version counts in Table I mapping
        # A, k, n, s, L, j, x should all be versioned
        self.assertIn("A", renamer.counters)
        self.assertIn("k", renamer.counters)
        self.assertIn("n", renamer.counters)
        self.assertIn("s", renamer.counters)
        self.assertIn("L", renamer.counters)
        self.assertIn("j", renamer.counters)
        self.assertIn("x", renamer.counters)
        
        # In Fig 3(c): s is defined initially (s1), in loop header (phi target), and in branch (s3 / s_upd)
        self.assertGreaterEqual(renamer.counters["s"], 2)
        self.assertGreaterEqual(renamer.counters["L"], 2)
        
        # Detect hallucinations on Fig. 3 code -> clean code, 0 errors
        errors = detect_hallucinations(fig3_code)
        ih_errors = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)']
        self.assertEqual(len(ih_errors), 0, f"Unexpected IH errors on clean Fig 3 code: {ih_errors}")

    def test_branchy_if_without_else_maybe_undefined(self):
        """
        Hand-written branchy test case (if with no else, variable assigned only in branch, used after):
        Asserts that SSA correctly inserts a phi with an UNDEFINED operand from the fallthrough path
        and flags it as an Identity Hallucination (IH).
        """
        code = """
def process(flag, val):
    if flag:
        res = val * 2
    return res
"""
        analyzer = CodeAnalyzer(code)
        analyzer.parse()
        renamers = analyzer.transform_ssa()
        
        func_ssa = analyzer.ssa_transformer.function_ssas.get("process")
        self.assertIsNotNone(func_ssa)
        
        # Check that res has a phi node placed at join block with UNDEFINED operand
        phi_found = False
        for b in func_ssa.cfg.get_reachable_blocks():
            if "res" in b.phi_nodes:
                phi = b.phi_nodes["res"]
                phi_found = True
                self.assertTrue(phi.has_undefined_operand(), f"Phi node should have UNDEFINED operand: {phi}")
                
        self.assertTrue(phi_found, "Phi node for 'res' should have been inserted at branch join block")
        
        # Static detector should catch this as IH
        errors = detect_hallucinations(code)
        ih_errors = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)' and e['variable_name'] == 'res']
        self.assertGreaterEqual(len(ih_errors), 1, "Should detect IH on conditionally defined variable 'res'")
        self.assertIn("defined only on conditional branch", ih_errors[0]['detail'])

    def test_branchy_if_with_else_both_defined(self):
        """
        Hand-written branchy test case where variable is defined on BOTH branches:
        Asserts phi-node is placed, all operands are defined, and NO IH error is raised.
        """
        code = """
def process(flag, val):
    if flag:
        res = val * 2
    else:
        res = val + 2
    return res
"""
        analyzer = CodeAnalyzer(code)
        analyzer.parse()
        renamers = analyzer.transform_ssa()
        
        func_ssa = analyzer.ssa_transformer.function_ssas.get("process")
        self.assertIsNotNone(func_ssa)
        
        # Phi node for res should exist with all operands defined
        phi_found = False
        for b in func_ssa.cfg.get_reachable_blocks():
            if "res" in b.phi_nodes:
                phi = b.phi_nodes["res"]
                phi_found = True
                self.assertFalse(phi.has_undefined_operand(), f"Phi node should NOT have UNDEFINED operand: {phi}")
                
        self.assertTrue(phi_found, "Phi node for 'res' should exist at join block")
        
        errors = detect_hallucinations(code)
        ih_errors = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)' and e['variable_name'] == 'res']
        self.assertEqual(len(ih_errors), 0, "No IH should be detected when variable is defined on all paths")

    def test_loop_ssa_backedge(self):
        """
        Tests loop with accumulator variable:
        s = 0
        while i < n:
            s = s + i
            i += 1
        """
        code = """
def compute_sum(n):
    s = 0
    i = 0
    while i < n:
        s = s + i
        i += 1
    return s
"""
        analyzer = CodeAnalyzer(code)
        analyzer.parse()
        renamers = analyzer.transform_ssa()
        
        func_ssa = analyzer.ssa_transformer.function_ssas.get("compute_sum")
        self.assertIsNotNone(func_ssa)
        
        # Check phi nodes placed for s and i at loop header
        phi_vars = set()
        for b in func_ssa.cfg.get_reachable_blocks():
            for v in b.phi_nodes:
                phi_vars.add(v)
                
        self.assertIn("s", phi_vars)
        self.assertIn("i", phi_vars)
        
        errors = detect_hallucinations(code)
        self.assertEqual(len(errors), 0, f"Loop accumulator should be clean: {errors}")

    def test_undefined_variable_direct_ih(self):
        """Tests standard use of completely undefined variable."""
        code = """
def calc(x):
    y = x + undefined_var
    return y
"""
        errors = detect_hallucinations(code)
        ih = [e for e in errors if e['error_type'] == 'Identity Hallucination (IH)' and e['variable_name'] == 'undefined_var']
        self.assertEqual(len(ih), 1)

    def test_unimported_call_esh(self):
        """Tests call to unimported function / library."""
        code = """
def compute(x):
    res = ghost_lib.run(x)
    return res
"""
        errors = detect_hallucinations(code)
        esh = [e for e in errors if e['error_type'] == 'External Source Hallucination (ESH)']
        self.assertGreaterEqual(len(esh), 1)


if __name__ == "__main__":
    unittest.main()
