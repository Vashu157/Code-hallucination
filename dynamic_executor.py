import traceback
import multiprocessing
import ast
import math
from typing import Dict, Any, List

def _run_test(source_code: str, test_cases_json: list, result_queue: multiprocessing.Queue):
    """
    Worker function to compile and execute the dynamically generated source code,
    then run all test cases. Runs in a separate process to allow for timeout enforcement.
    """
    exec_globals = {}
    
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
    try:
        tree = ast.parse(source_code)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                break
    except Exception:
        pass
        
    if not func_name or func_name not in exec_globals or not callable(exec_globals[func_name]):
        result_queue.put({
            "status": "error",
            "type": "Logical Failure Hallucination (LFH)",
            "type_code": "LFH",
            "message": f"Function '{func_name}' not found or not callable in the executed code."
        })
        return
        
    func = exec_globals[func_name]
    
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
        inputs = test.get("input", [])
        expected = test.get("expected_output")
        
        try:
            # Unpack inputs appropriately
            if isinstance(inputs, list):
                actual = func(*inputs)
            elif isinstance(inputs, dict):
                actual = func(**inputs)
            else:
                actual = func(inputs)
                
            if _outputs_match(actual, expected):
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
            # BUG-10 FIX: If expected_output is a string matching the raised exception's
            # type name (e.g. "ValueError"), treat this as a PASS not a crash.
            exc_type_name = type(e).__name__
            if isinstance(expected, str) and expected == exc_type_name:
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


def execute_dynamic_tests(source_code: str, test_cases_json: List[Dict[str, Any]], timeout: int = 5) -> Dict[str, Any]:
    """
    Safely executes dynamically generated source code against a set of JSON test cases.
    It catches exceptions and semantic failures, tagging them as LFH or LDH respectively.
    Enforces a strict timeout utilizing multiprocessing.
    """
    # Use 'spawn' to ensure clean, isolated process state (default on Windows)
    ctx = multiprocessing.get_context('spawn')
    result_queue = ctx.Queue()
    
    process = ctx.Process(target=_run_test, args=(source_code, test_cases_json, result_queue))
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
