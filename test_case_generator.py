import os
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Reads GOOGLE_API_KEY from environment / .env file
_api_key = os.environ.get("GOOGLE_API_KEY", "AIzaSyA4A4AiOWNsThw9kvxwOXta3iCZKTeqciE")
_client = genai.Client(api_key=_api_key)


def generate_test_cases(requirement_string: str, python_function_string: str) -> list:
    """
    Calls the Gemini API to generate Black-Box test cases based on Equivalence Class 
    Partitioning and Boundary Value Analysis.
    """
    prompt = f"""
    You are an expert QA automation engineer. Your task is to perform Black-Box testing 
    on the provided Python function based on the given user requirement. 
    
    You must use Equivalence Class Partitioning and Boundary Value Analysis to generate 
    exactly 10 unique test cases.
    
    User Requirement:
    {requirement_string}
    
    Python Function:
    {python_function_string}
    
    Return the output STRICTLY as a JSON array of exactly 10 objects. Each object must 
    have the following keys:
    - "input": A list containing the input arguments to the function.
    - "expected_output": The expected return value or output (can be a string indicating an Exception type if expected).
    """

    # Configure the API request to return pure JSON without markdown wrappers
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
    )

    # Generate content using the LLM
    response = _client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=config,
    )

    try:
        # Parse the raw JSON string
        test_cases = json.loads(response.text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON response: {e}\nResponse text: {response.text}")

    if not isinstance(test_cases, list):
        raise ValueError("The generated JSON is not an array.")

    # Validate that we have exactly / at least 10 tests generated
    if len(test_cases) < 10:
        raise ValueError(f"Failed to generate 10 test cases. Only {len(test_cases)} were generated. Please retry.")

    return test_cases

# --- Example Usage / Testing ---
if __name__ == "__main__":
    mock_requirement = "A function that calculates the square root of a positive number. If the number is negative, it raises a ValueError."
    mock_function = '''
import math
def calculate_sqrt(number):
    if number < 0:
        raise ValueError("Cannot calculate square root of a negative number")
    return math.sqrt(number)
'''
    try:
        print("Generating test cases via Gemini...")
        tests = generate_test_cases(mock_requirement, mock_function)
        print(f"Successfully generated {len(tests)} test cases:")
        print(json.dumps(tests, indent=2))
    except Exception as e:
        print(f"Error: {e}")
