import os
import json
import ast
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

# Optional Gemini API client initialization
_api_key = os.environ.get("GOOGLE_API_KEY", "AIzaSyA4A4AiOWNsThw9kvxwOXta3iCZKTeqciE")
_client = None

def _get_client():
    global _client
    if _client is None:
        try:
            from google import genai
            _client = genai.Client(api_key=_api_key)
        except Exception:
            _client = None
    return _client


def _fallback_ast_requirement_extraction(python_function_string: str) -> Dict[str, Any]:
    """Fallback AST-based requirement extractor when LLM is offline or mocked."""
    func_name = "unknown_func"
    params = []
    try:
        tree = ast.parse(python_function_string)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                params = [a.arg for a in node.args.args]
                break
    except Exception:
        pass

    return {
        "function_name": func_name,
        "parameters": params,
        "return_type": "Any",
        "preconditions": "Valid input arguments matching signature",
        "boundary_conditions": "Edge cases around 0, negative values, empty containers, large numbers",
        "exceptions": "Appropriate ValueError or TypeError on invalid input"
    }


def extract_requirements(requirement_string: str, python_function_string: str, client: Optional[Any] = None) -> Dict[str, Any]:
    """
    Algorithm 3 Step 1 (Requirement Analysis):
    Extracts structured requirements (function name, parameters, boundaries, exceptions)
    from the natural language prompt and code interface.
    """
    cli = client or _get_client()
    if cli is None:
        return _fallback_ast_requirement_extraction(python_function_string)

    prompt = f"""
You are an expert software test architect. Analyze the user requirement and Python function string below.
Extract the structured specification requirements.

User Requirement:
{requirement_string}

Python Function:
{python_function_string}

Return STRICTLY a JSON object with the following fields:
- "function_name": string (the exact function name to test)
- "parameters": list of strings (parameter names)
- "return_type": string (expected return type)
- "preconditions": string (valid input criteria)
- "boundary_conditions": string (critical edge cases, boundary values, empty inputs)
- "exceptions": string (expected exceptions if any)
"""
    try:
        from google.genai import types
        config = types.GenerateContentConfig(response_mime_type="application/json")
        response = cli.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        return json.loads(response.text)
    except Exception:
        return _fallback_ast_requirement_extraction(python_function_string)


def generate_test_cases_from_requirements(
    requirements: Dict[str, Any],
    python_function_string: str,
    feedback: Optional[str] = None,
    count: int = 10,
    client: Optional[Any] = None
) -> List[Dict[str, Any]]:
    """
    Algorithm 3 Step 2 (Test Case Generation & Refinement):
    Generates structured test cases based on extracted requirements, applying
    Equivalence Class Partitioning (ECP) and Boundary Value Analysis (BVA).
    Incorporates feedback from previous execution iterations if provided.
    """
    cli = client or _get_client()
    if cli is None:
        # Generate basic default test cases for offline/fallback mode
        func_name = requirements.get("function_name", "func")
        params = requirements.get("parameters", ["x"])
        dummy_tests = []
        for i in range(count):
            dummy_tests.append({
                "input": [i + 1] * len(params),
                "expected_output": None
            })
        return dummy_tests

    feedback_section = ""
    if feedback:
        feedback_section = f"""
PREVIOUS EXECUTION FEEDBACK (Refinement Iteration):
{feedback}
Please fix test expectations and add missing boundary test cases to address these issues.
"""

    prompt = f"""
You are an expert QA automation engineer. Perform Black-Box testing on the provided Python function
based on the structured requirements using Equivalence Class Partitioning (ECP) and Boundary Value Analysis (BVA).

Structured Requirements:
{json.dumps(requirements, indent=2)}

Python Function:
{python_function_string}
{feedback_section}
Generate exactly {count} unique test cases.
Return STRICTLY a JSON array of {count} objects, each with:
- "input": list of arguments to pass to the function.
- "expected_output": expected return value or string indicating expected Exception.
"""
    from google.genai import types
    config = types.GenerateContentConfig(response_mime_type="application/json")
    response = cli.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )

    test_cases = json.loads(response.text)
    if not isinstance(test_cases, list):
        raise ValueError("Generated test cases output is not a JSON array.")
    return test_cases


def generate_feedback(report: Dict[str, Any], coverage: int, c_min: int) -> str:
    """
    Algorithm 3 Step 5 (GenerateFeedback):
    Constructs a structured feedback summary from dynamic test execution results
    describing failures, crashes, and coverage shortfall.
    """
    feedback_lines = []

    if coverage < c_min:
        feedback_lines.append(
            f"- Coverage shortfall: only {coverage} test cases were provided, but at least {c_min} are required."
        )

    results = report.get("results", [])
    failed_count = report.get("failed_tests", 0)
    crashed_count = report.get("crashed_tests", 0)

    if failed_count > 0:
        feedback_lines.append(f"- {failed_count} test case(s) failed with Logical Deviation (LDH):")
        for res in results:
            if res.get("status") == "failed":
                feedback_lines.append(
                    f"  * Input: {res.get('input')} | Expected: {res.get('expected')} | Actual: {res.get('actual')}"
                )

    if crashed_count > 0:
        feedback_lines.append(f"- {crashed_count} test case(s) crashed with Logical Failure (LFH):")
        for res in results:
            if res.get("status") == "crashed":
                feedback_lines.append(
                    f"  * Input: {res.get('input')} | Error: {res.get('error')}"
                )

    if not feedback_lines:
        return "All tests passed and coverage criteria met."

    return "\n".join(feedback_lines)


# Backward-compatible wrapper
def generate_test_cases(requirement_string: str, python_function_string: str) -> List[Dict[str, Any]]:
    """Legacy helper executing Step 1 + Step 2 sequentially."""
    reqs = extract_requirements(requirement_string, python_function_string)
    return generate_test_cases_from_requirements(reqs, python_function_string, count=10)


if __name__ == "__main__":
    mock_req = "A function calculating the square root of positive numbers. Raises ValueError for negative numbers."
    mock_fn = """
import math
def calculate_sqrt(number):
    if number < 0:
        raise ValueError("Cannot calculate square root of a negative number")
    return math.sqrt(number)
"""
    reqs = extract_requirements(mock_req, mock_fn)
    print("Extracted Requirements:")
    print(json.dumps(reqs, indent=2))
    print("\nGenerating Test Cases...")
    tests = generate_test_cases_from_requirements(reqs, mock_fn, count=10)
    print(f"Generated {len(tests)} test cases.")
