# Phase 0 Baseline Audit Report

This report documents the baseline audit of the static and dynamic hallucination detection codebase per the project roadmap requirements.

---

## 1. Dead Code Inventory

- **CodeFeatureExtractor** (static_analysis.py) and **CodeAnalyzer.extract_features()**:
  - Legacy AST-only feature extraction class.
  - The detection pipeline (detect_hallucinations()) executes nalyzer.transform_ssa() directly, which constructs CFGs via CFGBuilder and builds SSA using SSATransformer and SSARenamer. CodeFeatureExtractor is never called.

---

## 2. Root Cause Analysis: Benchmark Errors (task_id 23–30)

In enchmark_report.json, records for tasks 23 through 30 each contain "pipeline_errors_this_run": 1.

- **Root Cause**: The dynamic test generation stage calls the Google Gemini API (gemini-2.5-flash). Successive rapid requests exhausted the free-tier rate limits (HTTP 429 ResourceExhausted).
- **Masking Vulnerability in enchmark.py**:
  `python
  total_found = report["summary"].get("total_hallucinations", 0)
  was_caught = total_found > 0
  `
  For tasks 23, 24, 27, and 28, static analysis detected an error (ESH or IH). Because 	otal_found > 0, the benchmark runner marked ug_caught: true, despite the dynamic execution pipeline having completely failed with an unhandled/caught pipeline error.

---

## 3. Scope & Precision Gaps Identified

1. **Class Methods & Closures**:
   - SSATransformer.transform() only iterated over top-level statements in 	ree.body. Any method enclosed within class Solution: or nested helper function was never converted to SSA, causing 100% false negatives for code written in classes.
2. **Expression Subtree Drops**:
   - SSARenamer._rename_expr_uses() did not inspect comprehensions ([x for x in ...]), lambdas (lambda x: ...), or ternary expressions ( if cond else b).
3. **Module-Level Variable False Positives**:
   - Top-level variables and class declarations were not populated in known_globals for child functions, causing false-positive Identity Hallucinations (IH) and External Source Hallucinations (ESH) on valid module references.
4. **Data Compliance & Structure Access (DCH/SAH)**:
   - Calling primitive integers or floats (x = 42; x()) was unhandled by DCH.
   - String out-of-bounds (s = "hi"; s[10]) and zero-step slices (s[::0]) were omitted from SAH.
