import traceback
import multiprocessing
import ast
import math
from typing import Dict, Any, List, Optional

def _run_test(
    source_code: str,
    test_cases_json: list,
    result_queue: multiprocessing.Queue,
    target_function: Optional[str] = None
):
    """
    Worker function to compile and execute the dynamically generated source code,
    then run all test cases. Runs in a separate process to allow for timeout enforcement.
    Supports both input/expected_output pairs and assertion-based test strings.
    """
    exec_globals = {}
    test_cases_json = test_cases_json or []
    
    # 1. Compile and execute source code to load it into exec_globals
    try:
        exec(source_code, exec_globals)
    except Exception as e:
        result_queue.put({
            "status": "error",
            "type": "Logical Failure Hallucination (LFH)",
            "type_code": "LFH",
            "message": "Source code failed to execute at module level (compilation/import crash).",
            "error": traceback.format_exc()
        })
        return

    # Find the function to test
    func_name = None
    if target_function and target_function in exec_globals and callable(exec_globals[target_function]):
        func_name = target_function
    else:
        try:
            tree = ast.parse(source_code)
            function_defs = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
            if target_function and target_function in function_defs:
                func_name = target_function
            elif function_defs:
                # Prefer the last non-private function (typical where helpers precede main solve function)
                public_funcs = [fn for fn in function_defs if not fn.startswith('_')]
                func_name = public_funcs[-1] if public_funcs else function_defs[-1]
        except Exception:
            pass
        
    func = exec_globals.get(func_name) if func_name else None
    
    report = {
        "status": "completed",
        "passed_tests": 0,
        "failed_tests": 0,
        "crashed_tests": 0,
        "results": []
    }

    def _outputs_match(actual: Any, expected: Any) -> bool:
        """BUG-9 FIX: Use math.isclose for float comparisons to avoid precision false LDH."""
        if isinstance(actual, float) and isinstance(expected, (int, float)):
            return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
        if isinstance(expected, float) and isinstance(actual, (int, float)):
            return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
        return actual == expected
    
    # 2. Run test cases
    for i, test in enumerate(test_cases_json):
        # A) Support assertion-based test strings (e.g. MBPP or CodeHalu assertions)
        is_assertion = isinstance(test, str) or (isinstance(test, dict) and ("assertion" in test or "test" in test))
        if is_assertion:
            assertion_str = test if isinstance(test, str) else (test.get("assertion") or test.get("test", ""))
            try:
                exec(assertion_str, exec_globals)
                report["passed_tests"] += 1
                report["results"].append({
                    "test_index": i,
                    "status": "passed",
                    "assertion": assertion_str,
                    "actual": "assertion passed"
                })
            except AssertionError:
                report["failed_tests"] += 1
                report["results"].append({
                    "test_index": i,
                    "status": "failed",
                    "type_code": "LDH",
                    "hallucination_type": "Logical Deviation Hallucination (LDH)",
                    "assertion": assertion_str,
                    "actual": "AssertionError"
                })
            except Exception as e:
                exc_name = type(e).__name__
                report["crashed_tests"] += 1
                report["results"].append({
                    "test_index": i,
                    "status": "crashed",
                    "type_code": "LFH",
                    "hallucination_type": "Logical Failure Hallucination (LFH)",
                    "assertion": assertion_str,
                    "error": exc_name,
                    "traceback": traceback.format_exc()
                })
            continue

        # B) Standard input/expected_output JSON pairs
        if not func or not callable(func):
            report["crashed_tests"] += 1
            report["results"].append({
                "test_index": i,
                "status": "crashed",
                "type_code": "LFH",
                "hallucination_type": "Logical Failure Hallucination (LFH)",
                "error": f"Function '{func_name}' not found or not callable."
            })
            continue

        inputs = test.get("input", [])
        expected = test.get("expected_output")
        is_crash_only = test.get("check_crash_only", False) or expected == "<ANY>"
        
        try:
            # Unpack inputs appropriately
            if isinstance(inputs, list):
                try:
                    actual = func(*inputs)
                except TypeError as te:
                    # If func expects 1 argument and inputs is a list (e.g. func(arr)), try func(inputs)
                    if "positional argument" in str(te):
                        actual = func(inputs)
                    else:
                        raise
            elif isinstance(inputs, dict):
                actual = func(**inputs)
            else:
                actual = func(inputs)
                
            if is_crash_only or _outputs_match(actual, expected):
                report["passed_tests"] += 1
                report["results"].append({
                    "test_index": i,
                    "status": "passed",
                    "input": inputs,
                    "expected": expected,
                    "actual": actual
                })
            else:
                report["failed_tests"] += 1
                report["results"].append({
                    "test_index": i,
                    "status": "failed",
                    "type_code": "LDH",
                    "hallucination_type": "Logical Deviation Hallucination (LDH)",
                    "input": inputs,
                    "expected": expected,
                    "actual": actual
                })
        except Exception as e:
            exc_type_name = type(e).__name__
            # Flexible exception matching (e.g. "ValueError", "raises ValueError", "Exception")
            is_expected_exc = False
            if isinstance(expected, str):
                exp_clean = expected.strip()
                if (exp_clean == exc_type_name or
                    exc_type_name in exp_clean or
                    exp_clean.lower() in exc_type_name.lower() or
                    exc_type_name.lower() in exp_clean.lower()):
                    is_expected_exc = True

            if is_expected_exc:
                report["passed_tests"] += 1
                report["results"].append({
                    "test_index": i,
                    "status": "passed",
                    "input": inputs,
                    "expected": expected,
                    "actual": f"raised {exc_type_name} (expected)"
                })
            else:
                report["crashed_tests"] += 1
                report["results"].append({
                    "test_index": i,
                    "status": "crashed",
                    "type_code": "LFH",
                    "hallucination_type": "Logical Failure Hallucination (LFH)",
                    "input": inputs,
                    "expected": expected,
                    "error": exc_type_name,
                    "traceback": traceback.format_exc()
                })
            
    result_queue.put(report)


def execute_dynamic_tests(
    source_code: str,
    test_cases_json: List[Dict[str, Any]],
    timeout: int = 5,
    target_function: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely executes dynamically generated source code against a set of JSON test cases.
    It catches exceptions and semantic failures, tagging them as LFH or LDH respectively.
    Enforces a strict timeout utilizing multiprocessing.
    """
    # Use 'spawn' to ensure clean, isolated process state (default on Windows)
    ctx = multiprocessing.get_context('spawn')
    result_queue = ctx.Queue()
    
    process = ctx.Process(
        target=_run_test,
        args=(source_code, test_cases_json, result_queue, target_function)
    )
    process.start()
    
    # Wait for the process to finish within the timeout
    process.join(timeout)
    
    if process.is_alive():
        # Force terminate if it loops infinitely
        process.terminate()
        process.join()
        return {
            "status": "error",
            "type": "Logical Failure Hallucination (LFH)",
            "type_code": "LFH",
            "message": f"Execution exceeded timeout of {timeout} seconds.",
            "error": "TimeoutError"
        }

    # BUG-12 FIX: Use result_queue.get(timeout=2) instead of checking .empty() first.
    # The .empty() check is unreliable: the OS pipe buffer may not have been fully
    # flushed when the parent reads it immediately after process.join().
    try:
        return result_queue.get(timeout=2)
    except Exception:
        return {
            "status": "error",
            "type": "Logical Failure Hallucination (LFH)",
            "type_code": "LFH",
            "message": "The execution process crashed unexpectedly without returning results."
        }

# --- Example Usage / Mock Test ---
if __name__ == "__main__":
    import json
    
    # Mock LLM generated python function (with a subtle bug for LDH, and one crash case for LFH)
    mock_source = """
def is_even(num):
    if num == 999:
        raise ValueError("I crash on 999!")
    # Subtle bug: incorrectly returns True for 5 (LDH)
    if num == 5:
        return True
    return num % 2 == 0
"""
    
    # Mock JSON test cases
    mock_tests = [
        {"input": [2], "expected_output": True},      # Pass
        {"input": [3], "expected_output": False},     # Pass
        {"input": [5], "expected_output": False},     # Fail (LDH)
        {"input": [999], "expected_output": False},   # Crash (LFH)
    ]
    
    print("Executing dynamic tests...")
    report = execute_dynamic_tests(mock_source, mock_tests)
    print(json.dumps(report, indent=2))
