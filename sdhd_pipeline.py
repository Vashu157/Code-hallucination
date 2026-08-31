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
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable

from static_analysis import detect_hallucinations
from test_case_generator import (
    extract_requirements,
    generate_test_cases_from_requirements,
    generate_feedback,
    generate_test_cases
)
from dynamic_executor import execute_dynamic_tests


class SDHD_Pipeline:
    """
    Static-Dynamic Hallucination Detection (SDHD) Pipeline.
    Implements Algorithm 3 refinement loop and full static hallucination detection.
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
    # Step 1 – Static Analysis
    # ------------------------------------------------------------------
    def _run_static_analysis(self, generated_code: str) -> List[Dict[str, Any]]:
        """
        Runs SSA-based static analysis on the generated code.
        Returns a normalized list of static hallucination records.
        """
        raw_errors = detect_hallucinations(generated_code)
        normalized = []
        for err in raw_errors:
            normalized.append({
                "source": "static",
                "error_type": err.get("error_type", "Unknown"),
                "variable_name": err.get("variable_name", "unknown"),
                "line_number": err.get("line_number"),
                "detail": err.get("detail"),
            })
        return normalized

    # ------------------------------------------------------------------
    # Step 2 – Dynamic Execution Stage (Algorithm 3)
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
                feedback = generate_feedback({}, coverage, self.c_min)
                continue

            # Step 4: Dynamic execution
            report = execute_dynamic_tests(generated_code, test_cases, timeout=self.timeout)
            passed = report.get("passed_tests", 0)
            failed = report.get("failed_tests", 0)
            crashed = report.get("crashed_tests", 0)

            # Extract normalized hallucination records
            current_hallucinations = []
            if report.get("status") == "error":
                current_hallucinations.append({
                    "source": "dynamic",
                    "error_type": report.get("type", "Logical Failure Hallucination (LFH)"),
                    "variable_name": "execution_environment",
                    "line_number": None,
                    "detail": report.get("message"),
                })
            else:
                for res in report.get("results", []):
                    if res["status"] == "failed":
                        current_hallucinations.append({
                            "source": "dynamic",
                            "error_type": res.get("hallucination_type", "Logical Deviation Hallucination (LDH)"),
                            "variable_name": f"test_index_{res['test_index']}",
                            "line_number": None,
                            "detail": f"Input: {res.get('input')} | Expected: {res.get('expected')} | Actual: {res.get('actual')}",
                        })
                    elif res["status"] == "crashed":
                        current_hallucinations.append({
                            "source": "dynamic",
                            "error_type": res.get("hallucination_type", "Logical Failure Hallucination (LFH)"),
                            "variable_name": f"test_index_{res['test_index']}",
                            "line_number": None,
                            "detail": f"Input: {res.get('input')} | Error: {res.get('error')}",
                        })

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
    # Deduplication
    # ------------------------------------------------------------------
    @staticmethod
    def _deduplicate(hallucinations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Removes duplicate hallucination entries by creating a fingerprint
        based on (error_type, variable_name, line_number).
        """
        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for item in hallucinations:
            key = (
                item.get("error_type"),
                item.get("variable_name"),
                item.get("line_number"),
            )
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

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

        Args:
            user_prompt:    The natural-language requirement.
            generated_code: The Python source code string.
            test_gen_fn:    Optional custom/mock test generator function for testing.

        Returns:
            A comprehensive hallucination detection report as a dictionary.
        """
        report: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": {},
            "hallucinations": [],
            "errors": [],
        }

        all_hallucinations: List[Dict[str, Any]] = []

        # --- Stage 1: Static Analysis ---
        print("[SDHD] Running static analysis...")
        try:
            static_results = self._run_static_analysis(generated_code)
            all_hallucinations.extend(static_results)
            print(f"[SDHD] Static analysis complete: {len(static_results)} issue(s) found.")
        except Exception as e:
            report["errors"].append({"stage": "static", "error": str(e)})
            print(f"[SDHD] Static analysis failed: {e}")

        # --- Stage 2 & 3: Dynamic Pipeline (Algorithm 3) ---
        dynamic_res = {}
        try:
            dynamic_res = self._run_dynamic_pipeline(user_prompt, generated_code, test_gen_fn=test_gen_fn)
            all_hallucinations.extend(dynamic_res.get("hallucinations", []))
        except Exception as e:
            report["errors"].append({"stage": "dynamic", "error": str(e)})
            print(f"[SDHD] Dynamic pipeline failed: {e}")

        # --- Stage 4: Deduplication ---
        unique_hallucinations = self._deduplicate(all_hallucinations)

        # --- Build Summary ---
        static_count = sum(1 for h in unique_hallucinations if h["source"] == "static")
        dynamic_count = sum(1 for h in unique_hallucinations if h["source"] == "dynamic")
        type_counts: Dict[str, int] = {}
        for h in unique_hallucinations:
            etype = h["error_type"]
            type_counts[etype] = type_counts.get(etype, 0) + 1

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

    pipeline = SDHD_Pipeline(timeout=5, c_min=10, i_max=3)
    result = pipeline.run(user_prompt=mock_requirement, generated_code=mock_code)

    print("\n--- SDHD Pipeline Final Report ---")
    print(json.dumps(result, indent=2))
