"""
SDHD_Pipeline: Static + Dynamic Hallucination Detection Pipeline
================================================================
Orchestrates the full end-to-end hallucination detection workflow:
  1. Static analysis via StaticDetector (SSA-based)
  2. LLM-generated test cases via Gemini (black-box ECP/BVA testing)
  3. Dynamic execution via execute_dynamic_tests (safe subprocess sandbox)
  4. Deduplication and final JSON summary report
"""

import json
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from static_analysis import detect_hallucinations
from test_case_generator import generate_test_cases
from dynamic_executor import execute_dynamic_tests


class SDHD_Pipeline:
    """
    Static-Dynamic Hallucination Detection (SDHD) Pipeline.
    Integrates static SSA-based analysis and dynamic LLM-driven execution testing
    to produce a comprehensive hallucination detection report.
    """

    def __init__(self, timeout: int = 5, max_retries: int = 3, retry_delay: float = 15.0) -> None:
        """
        Args:
            timeout:     Seconds before a dynamic test execution is killed (TimeoutError).
            max_retries: How many times to retry the LLM if it fails to produce 10 tests.
            retry_delay: Base delay in seconds between LLM retries. Doubles on each attempt
                         (exponential backoff). Overridden by Retry-After hint from the API.
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

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
                "detail": None,
            })
        return normalized

    # ------------------------------------------------------------------
    # Step 2 – Test Case Generation (with retry)
    # ------------------------------------------------------------------
    def _generate_test_cases(self, user_prompt: str, generated_code: str) -> List[Dict[str, Any]]:
        """
        Calls the Gemini API to produce black-box test cases.
        Retries up to `max_retries` times with exponential backoff.
        Automatically honours the Retry-After delay from 429 responses.
        """
        last_exception: Optional[Exception] = None
        delay = self.retry_delay

        for attempt in range(1, self.max_retries + 1):
            try:
                tests = generate_test_cases(user_prompt, generated_code)
                return tests
            except Exception as e:
                last_exception = e
                error_msg = str(e)

                # Parse retry-after seconds from the 429 error message if present
                wait = delay
                retry_match = re.search(r'retry[_\s]?in[\s:]+(\d+(?:\.\d+)?)\s*s', error_msg, re.IGNORECASE)
                if retry_match:
                    wait = float(retry_match.group(1)) + 2.0  # add a small buffer

                if attempt < self.max_retries:
                    print(f"[SDHD] Test generation attempt {attempt}/{self.max_retries} failed. "
                          f"Retrying in {wait:.1f}s... ({type(e).__name__})")
                    time.sleep(wait)
                    delay = min(delay * 2, 120.0)  # exponential backoff, cap at 2 min
                else:
                    print(f"[SDHD] Test generation attempt {attempt}/{self.max_retries} failed: {e}")

        raise RuntimeError(
            f"Test case generation failed after {self.max_retries} retries. "
            f"Last error: {last_exception}"
        )

    # ------------------------------------------------------------------
    # Step 3 – Dynamic Execution
    # ------------------------------------------------------------------
    def _run_dynamic_analysis(
        self, generated_code: str, test_cases: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Executes the generated code against all test cases in a sandboxed process.
        Returns a normalized list of dynamic hallucination records.
        """
        report = execute_dynamic_tests(generated_code, test_cases, timeout=self.timeout)

        hallucinations = []
        results = report.get("results", [])

        if report.get("status") == "error":
            # Entire execution environment crashed
            hallucinations.append({
                "source": "dynamic",
                "error_type": report.get("type", "Logical Failure Hallucination (LFH)"),
                "variable_name": "execution_environment",
                "line_number": None,
                "detail": report.get("message"),
            })
            return hallucinations

        for result in results:
            if result["status"] == "failed":
                hallucinations.append({
                    "source": "dynamic",
                    "error_type": result.get("hallucination_type", "Logical Deviation Hallucination (LDH)"),
                    "variable_name": f"test_index_{result['test_index']}",
                    "line_number": None,
                    "detail": (
                        f"Input: {result.get('input')}, "
                        f"Expected: {result.get('expected')}, "
                        f"Actual: {result.get('actual')}"
                    ),
                })
            elif result["status"] == "crashed":
                hallucinations.append({
                    "source": "dynamic",
                    "error_type": result.get("hallucination_type", "Logical Failure Hallucination (LFH)"),
                    "variable_name": f"test_index_{result['test_index']}",
                    "line_number": None,
                    "detail": (
                        f"Input: {result.get('input')}, "
                        f"Error: {result.get('error')}"
                    ),
                })

        return hallucinations

    # ------------------------------------------------------------------
    # Step 4 – Deduplication
    # ------------------------------------------------------------------
    @staticmethod
    def _deduplicate(hallucinations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Removes duplicate hallucination entries by creating a fingerprint
        based on (error_type, variable_name, line_number).
        Static entries take precedence in the output order.
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
    def run(self, user_prompt: str, generated_code: str) -> Dict[str, Any]:
        """
        Orchestrates the full SDHD pipeline end-to-end.

        Args:
            user_prompt:    The original natural-language requirement the LLM was given.
            generated_code: The Python source code string produced by the LLM.

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

        # --- Stage 1: Static ---
        print("[SDHD] Running static analysis...")
        try:
            static_results = self._run_static_analysis(generated_code)
            all_hallucinations.extend(static_results)
            print(f"[SDHD] Static analysis complete: {len(static_results)} issue(s) found.")
        except Exception as e:
            report["errors"].append({"stage": "static", "error": str(e)})
            print(f"[SDHD] Static analysis failed: {e}")

        # --- Stage 2: Test Case Generation ---
        test_cases: List[Dict[str, Any]] = []
        print("[SDHD] Generating test cases via Gemini...")
        try:
            test_cases = self._generate_test_cases(user_prompt, generated_code)
            print(f"[SDHD] {len(test_cases)} test cases generated.")
        except Exception as e:
            report["errors"].append({"stage": "test_generation", "error": str(e)})
            print(f"[SDHD] Test case generation failed: {e}")

        # --- Stage 3: Dynamic ---
        if test_cases:
            print("[SDHD] Running dynamic execution tests...")
            try:
                dynamic_results = self._run_dynamic_analysis(generated_code, test_cases)
                all_hallucinations.extend(dynamic_results)
                print(f"[SDHD] Dynamic analysis complete: {len(dynamic_results)} issue(s) found.")
            except Exception as e:
                report["errors"].append({"stage": "dynamic", "error": str(e)})
                print(f"[SDHD] Dynamic analysis failed: {e}")

        # --- Stage 4: Deduplication ---
        unique_hallucinations = self._deduplicate(all_hallucinations)

        # --- Build Summary ---
        static_count = sum(1 for h in unique_hallucinations if h["source"] == "static")
        dynamic_count = sum(1 for h in unique_hallucinations if h["source"] == "dynamic")
        type_counts: Dict[str, int] = {}
        for h in unique_hallucinations:
            etype = h["error_type"]
            type_counts[etype] = type_counts.get(etype, 0) + 1

        report["summary"] = {
            "total_hallucinations": len(unique_hallucinations),
            "static_detections": static_count,
            "dynamic_detections": dynamic_count,
            "test_cases_run": len(test_cases),
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

    pipeline = SDHD_Pipeline(timeout=5, max_retries=2)
    result = pipeline.run(user_prompt=mock_requirement, generated_code=mock_code)

    print("\n--- SDHD Pipeline Final Report ---")
    print(json.dumps(result, indent=2))
