"""
SDHD_Pipeline: Static + Dynamic Hallucination Detection Pipeline
================================================================
Orchestrates the full end-to-end hallucination detection workflow per Paper Algorithms 1-3:
  1. Static analysis via StaticDetector (SSA + CFG-based for 6 static types: DCH, SAH, IH, ESH, PCH, CBH)
  2. Algorithm 3 Dynamic Detection Pipeline:
     - Step 1: Requirement Analysis (extracts function signature, boundary conditions, exceptions)
     - Step 2: Test Case Generation via ECP / BVA
     - Step 3: Coverage Gate evaluation (Coverage >= C_min)
     - Step 4: Sandboxed Dynamic Execution
     - Step 5: Iterative Refinement Feedback Loop (up to I_max iterations)
  3. Deduplication and final structured JSON summary report
"""

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable

from static_analysis import detect_hallucinations
from test_case_generator import (
    extract_requirements,
    generate_test_cases_from_requirements,
    generate_feedback,
    generate_test_cases
)
from dynamic_executor import execute_dynamic_tests


# =====================================================================
# 8-Type Hallucination Taxonomy (Section III-D & Table VII)
# =====================================================================

TAXONOMY_STATIC = {
    "DCH": "Data Compliance Hallucination (DCH)",
    "SAH": "Structure Access Hallucination (SAH)",
    "IH": "Identity Hallucination (IH)",
    "ESH": "External Source Hallucination (ESH)",
    "PCH": "Physical Constraint Hallucination (PCH)",
    "CBH": "Computational Boundary Hallucination (CBH)",
}

TAXONOMY_DYNAMIC = {
    "LDH": "Logical Deviation Hallucination (LDH)",
    "LFH": "Logical Failure Hallucination (LFH)",  # Also referred to as LBH in early text, normalized to LFH per Table VII
}

ALL_TAXONOMY_CODES = ["DCH", "SAH", "IH", "ESH", "PCH", "CBH", "LDH", "LFH"]

TAXONOMY_MAP = {**TAXONOMY_STATIC, **TAXONOMY_DYNAMIC}

TAXONOMY_SOURCES = {
    "DCH": "static",
    "SAH": "static",
    "IH": "static",
    "ESH": "static",
    "PCH": "static",
    "CBH": "static",
    "LDH": "dynamic",
    "LFH": "dynamic",
}


def get_type_code(error_type_or_code: str) -> str:
    """Extracts the canonical 3-letter uppercase type code from any taxonomy string."""
    if not error_type_or_code:
        return "UNKNOWN"
    s = str(error_type_or_code).strip()
    if s in TAXONOMY_MAP:
        return s
    if s.upper() == "LBH":
        return "LFH"
    m = re.search(r'\b(DCH|SAH|IH|ESH|PCH|CBH|LDH|LFH|LBH)\b', s, re.IGNORECASE)
    if m:
        code = m.group(1).upper()
        return "LFH" if code == "LBH" else code
    return "UNKNOWN"


def normalize_hallucination_record(raw: Dict[str, Any], default_source: str = "static") -> Dict[str, Any]:
    """
    Normalizes any static or dynamic detection dict into the canonical record format (Section III-E).
    Guarantees: source, type_code, error_type, location, variable_name, line_number, detail.
    """
    raw_type = (
        raw.get("type_code")
        or raw.get("error_type")
        or raw.get("hallucination_type")
        or raw.get("type")
        or "UNKNOWN"
    )
    type_code = get_type_code(raw_type)
    error_type = TAXONOMY_MAP.get(type_code, str(raw_type))
    source = raw.get("source") or TAXONOMY_SOURCES.get(type_code, default_source)

    location = raw.get("location") or raw.get("variable_name") or "unknown"
    line_number = raw.get("line_number")
    detail = raw.get("detail") or raw.get("message") or ""

    return {
        "source": source,
        "type_code": type_code,
        "error_type": error_type,
        "location": str(location),
        "variable_name": str(location),  # backwards compatibility alias
        "line_number": line_number,
        "detail": str(detail),
    }


def aggregate_and_deduplicate(
    static_results: List[Dict[str, Any]],
    dynamic_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Implements Section III-E aggregation:
      D_Output = O1 U O2 with deduplication on (location, content / fingerprint).
    """
    all_normalized: List[Dict[str, Any]] = []
    for item in static_results:
        all_normalized.append(normalize_hallucination_record(item, default_source="static"))
    for item in dynamic_results:
        all_normalized.append(normalize_hallucination_record(item, default_source="dynamic"))

    seen: set = set()
    unique: List[Dict[str, Any]] = []

    for rec in all_normalized:
        detail_snippet = " ".join(rec["detail"].strip().split())
        fingerprint = (
            rec["type_code"],
            rec["location"],
            rec["line_number"],
            detail_snippet
        )
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(rec)

    return unique


class SDHD_Pipeline:
    """
    Static-Dynamic Hallucination Detection (SDHD) Pipeline.
    Implements Section III-D/E aggregation and Algorithm 3 refinement loop.
    """

    def __init__(
        self,
        timeout: int = 5,
        max_retries: int = 3,
        retry_delay: float = 15.0,
        c_min: int = 10,
        i_max: int = 3
    ) -> None:
        """
        Args:
            timeout:     Seconds before a dynamic test execution is killed (TimeoutError).
            max_retries: Retries for API transient/network errors.
            retry_delay: Delay in seconds between API retries.
            c_min:       Coverage threshold (minimum test cases required, default 10).
            i_max:       Maximum refinement iterations before exhaustion (default 3).
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.c_min = c_min
        self.i_max = i_max

    # ------------------------------------------------------------------
    # Step 1 – Static Analysis (O1)
    # ------------------------------------------------------------------
    def _run_static_analysis(self, generated_code: str) -> List[Dict[str, Any]]:
        """
        Runs SSA-based static analysis on the generated code.
        Returns a normalized list of static hallucination records.
        """
        raw_errors = detect_hallucinations(generated_code)
        normalized = []
        for err in raw_errors:
            normalized.append(normalize_hallucination_record(err, default_source="static"))
        return normalized

    # ------------------------------------------------------------------
    # Step 2 – Dynamic Execution Stage (Algorithm 3) (O2)
    # ------------------------------------------------------------------
    def _run_dynamic_pipeline(
        self,
        user_prompt: str,
        generated_code: str,
        test_gen_fn: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Executes Algorithm 3:
        1. Requirement Extraction
        2. Iterative loop up to I_max with coverage gate C_min & feedback refinement
        """
        requirements = extract_requirements(user_prompt, generated_code)
        feedback: Optional[str] = None
        last_test_cases: List[Dict[str, Any]] = []
        last_dynamic_hallucinations: List[Dict[str, Any]] = []
        iterations_run = 0

        for iteration in range(1, self.i_max + 1):
            iterations_run = iteration
            print(f"[SDHD] Dynamic Pipeline: Iteration {iteration}/{self.i_max}")

            # Generate test cases (with retry for network)
            test_cases: List[Dict[str, Any]] = []
            delay = self.retry_delay

            for attempt in range(1, self.max_retries + 1):
                try:
                    if test_gen_fn is not None:
                        test_cases = test_gen_fn(requirements, generated_code, feedback, self.c_min)
                    else:
                        test_cases = generate_test_cases_from_requirements(
                            requirements, generated_code, feedback=feedback, count=self.c_min
                        )
                    break
                except Exception as e:
                    if attempt < self.max_retries:
                        time.sleep(min(delay, 10.0))
                        delay *= 2
                    else:
                        print(f"[SDHD] Test generation error on iteration {iteration}: {e}")

            last_test_cases = test_cases
            coverage = len(test_cases)

            # Step 3: Coverage gate evaluation
            if coverage < self.c_min:
                print(f"[SDHD] Coverage shortfall ({coverage} < {self.c_min}). Generating feedback...")
                # BUG-14 FIX: The previous `last_dynamic_hallucinations and X or Y` expression
                # was inverted: when hallucinations list was non-empty it fed a fake empty report,
                # discarding actual context. Coverage shortfall always uses a fixed shortfall report.
                feedback = generate_feedback({"results": [], "status": "shortfall"}, coverage, self.c_min)

                continue

            # Step 4: Dynamic execution
            report = execute_dynamic_tests(generated_code, test_cases, timeout=self.timeout)
            passed = report.get("passed_tests", 0)
            failed = report.get("failed_tests", 0)
            crashed = report.get("crashed_tests", 0)

            # Extract normalized hallucination records
            current_hallucinations = []
            if report.get("status") == "error":
                current_hallucinations.append(normalize_hallucination_record({
                    "source": "dynamic",
                    "type_code": "LFH",
                    "error_type": report.get("type", "Logical Failure Hallucination (LFH)"),
                    "location": "execution_environment",
                    "line_number": None,
                    "detail": report.get("message", "Dynamic execution environment failure."),
                }, default_source="dynamic"))
            else:
                for res in report.get("results", []):
                    if res["status"] == "failed":
                        current_hallucinations.append(normalize_hallucination_record({
                            "source": "dynamic",
                            "type_code": res.get("type_code", "LDH"),
                            "error_type": res.get("hallucination_type", "Logical Deviation Hallucination (LDH)"),
                            "location": f"test_index_{res['test_index']}",
                            "line_number": None,
                            "detail": f"Input: {res.get('input')} | Expected: {res.get('expected')} | Actual: {res.get('actual')}",
                        }, default_source="dynamic"))
                    elif res["status"] == "crashed":
                        current_hallucinations.append(normalize_hallucination_record({
                            "source": "dynamic",
                            "type_code": res.get("type_code", "LFH"),
                            "error_type": res.get("hallucination_type", "Logical Failure Hallucination (LFH)"),
                            "location": f"test_index_{res['test_index']}",
                            "line_number": None,
                            "detail": f"Input: {res.get('input')} | Error: {res.get('error')}",
                        }, default_source="dynamic"))

            last_dynamic_hallucinations = current_hallucinations

            # Step 5: Check PASS condition
            if passed == coverage and coverage >= self.c_min:
                print(f"[SDHD] Dynamic Stage PASS: All {coverage} test cases passed on iteration {iteration}.")
                return {
                    "status": "PASS",
                    "hallucinations": [],
                    "iterations": iterations_run,
                    "test_cases_run": coverage,
                    "requirements": requirements
                }

            # If errors present and more iterations allowed, generate feedback and refine
            if iteration < self.i_max:
                feedback = generate_feedback(report, coverage, self.c_min)
                print(f"[SDHD] Iteration {iteration} encountered issues ({failed} failed, {crashed} crashed). Refining...")

        # Loop exhausted without full PASS
        print(f"[SDHD] Algorithm 3 exhausted after {self.i_max} iterations -> POTENTIAL_HALLUCINATION.")
        return {
            "status": "POTENTIAL_HALLUCINATION",
            "hallucinations": last_dynamic_hallucinations,
            "iterations": iterations_run,
            "test_cases_run": len(last_test_cases),
            "requirements": requirements
        }

    # ------------------------------------------------------------------
    # Deduplication & Aggregation (Section III-E)
    # ------------------------------------------------------------------
    @staticmethod
    def _deduplicate(hallucinations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Removes duplicate hallucination entries using canonical fingerprinting.
        BUG-15 FIX: Previously called aggregate_and_deduplicate(hallucinations, []) which forced
        default_source="static" on ALL input records (including dynamic ones), corrupting the source field.
        Now partitions records by existing 'source' field to preserve correctness.
        """
        static_recs = [r for r in hallucinations if r.get("source") != "dynamic"]
        dynamic_recs = [r for r in hallucinations if r.get("source") == "dynamic"]
        return aggregate_and_deduplicate(static_recs, dynamic_recs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(
        self,
        user_prompt: str,
        generated_code: str,
        test_gen_fn: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Orchestrates the full SDHD pipeline end-to-end.
        Aggregates static (O1) and dynamic (O2) findings into D_Output = O1 U O2.

        Args:
            user_prompt:    The natural-language requirement.
            generated_code: The Python source code string.
            test_gen_fn:    Optional custom/mock test generator function for testing.

        Returns:
            A comprehensive hallucination detection report as a dictionary.
        """
        report: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {},
            "hallucinations": [],
            "stages": {},
            "errors": [],
        }

        static_results: List[Dict[str, Any]] = []
        dynamic_results: List[Dict[str, Any]] = []
        static_failed = False
        dynamic_failed = False

        # --- Stage 1: Static Analysis (O1) ---
        print("[SDHD] Running static analysis...")
        try:
            static_results = self._run_static_analysis(generated_code)
            print(f"[SDHD] Static analysis complete: {len(static_results)} issue(s) found.")
        except Exception as e:
            static_failed = True
            report["errors"].append({"stage": "static", "error": str(e)})
            print(f"[SDHD] Static analysis failed: {e}")

        # --- Stage 2 & 3: Dynamic Pipeline (Algorithm 3) (O2) ---
        dynamic_res: Dict[str, Any] = {}
        try:
            dynamic_res = self._run_dynamic_pipeline(user_prompt, generated_code, test_gen_fn=test_gen_fn)
            dynamic_results = dynamic_res.get("hallucinations", [])
        except Exception as e:
            dynamic_failed = True
            report["errors"].append({"stage": "dynamic", "error": str(e)})
            print(f"[SDHD] Dynamic pipeline failed: {e}")

        # --- Stage 4: Formal Aggregation & Deduplication (Section III-E: D_Output = O1 U O2) ---
        unique_hallucinations = aggregate_and_deduplicate(static_results, dynamic_results)

        # --- Build Summary & 8-Type Breakdown ---
        static_count = sum(1 for h in unique_hallucinations if h["source"] == "static")
        dynamic_count = sum(1 for h in unique_hallucinations if h["source"] == "dynamic")

        # Initialize all 8 categories with 0 per Section III-D
        type_counts: Dict[str, int] = {code: 0 for code in ALL_TAXONOMY_CODES}
        for h in unique_hallucinations:
            tcode = h.get("type_code")
            if tcode in type_counts:
                type_counts[tcode] += 1
            # BUG-13 FIX: UNKNOWN type_codes are silently skipped — they are counted in
            # total_hallucinations but must NOT insert new keys into the fixed 8-key breakdown dict.


        overall_status = "PASS" if len(unique_hallucinations) == 0 else "POTENTIAL_HALLUCINATION"

        report["summary"] = {
            "overall_status": overall_status,
            "total_hallucinations": len(unique_hallucinations),
            "static_detections": static_count,
            "dynamic_detections": dynamic_count,
            "dynamic_status": dynamic_res.get("status", "UNKNOWN"),
            "refinement_iterations": dynamic_res.get("iterations", 0),
            "test_cases_run": dynamic_res.get("test_cases_run", 0),
            "breakdown_by_type": type_counts,
        }
        report["hallucinations"] = unique_hallucinations
        report["stages"] = {
            "static": {
                "status": "ERROR" if static_failed else "COMPLETED",
                "count": len(static_results),
                "detections": static_results,
            },
            "dynamic": {
                "status": "ERROR" if dynamic_failed else dynamic_res.get("status", "UNKNOWN"),
                "iterations": dynamic_res.get("iterations", 0),
                "test_cases_run": dynamic_res.get("test_cases_run", 0),
                "requirements": dynamic_res.get("requirements", {}),
                "count": len(dynamic_results),
                "detections": dynamic_results,
            }
        }

        return report


# --- Example Usage ---
if __name__ == "__main__":
    mock_requirement = (
        "A function that takes two numbers and returns their integer division result. "
        "It should raise a ZeroDivisionError if the divisor is zero."
    )

    mock_code = """
def int_divide(a, b):
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero.")
    return a // b
"""

    def mock_test_gen(reqs, code, feedback, count):
        tests = [{"input": [i * 2, 2], "expected_output": i} for i in range(count - 1)]
        tests.append({"input": [5, 0], "expected_output": "ZeroDivisionError"})
        return tests

    pipeline = SDHD_Pipeline(timeout=5, c_min=10, i_max=3)
    result = pipeline.run(user_prompt=mock_requirement, generated_code=mock_code, test_gen_fn=mock_test_gen)

    print("\n--- SDHD Pipeline Final Report ---")
    print(json.dumps(result, indent=2))

