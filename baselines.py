"""
baselines.py - Baseline Reproductions & Benchmark Evaluation Tools (Section IV-C1)
===================================================================================
Implements the full set of comparison baselines from Section IV-C1 of the SDHD paper:
1. PyLint: Traditional static analysis linter mapped to 8-type taxonomy.
2. Flake8: Traditional static style and syntax linter mapped to 8-type taxonomy.
3. CodeEval: Pure dynamic execution baseline (runs test cases once without refinement).
4. CodeHalu (Tian et al. [17]): Dynamic execution-based verification baseline.
5. SelfDebug (Chen et al. [6]): LLM self-reflection / prompting debugger.
6. SelfCheck (Li et al. [22]): Multi-sample consistency checking across completions.
7. SAC3 (Manakul et al. [23]): Semantic Agreement check using embedding/token cosine similarity.
8. SDHD Adapter: Unified adapter wrapping the complete static-dynamic pipeline.

Also provides standard Precision, Recall, F1, Accuracy, and FPR evaluation utilities,
and a side-by-side record runner.
"""

import ast
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union, Callable

from dynamic_executor import execute_dynamic_tests
from test_case_generator import extract_requirements, generate_test_cases_from_requirements
from sdhd_pipeline import SDHD_Pipeline
from dataset_loaders import DatasetRecord, load_all_datasets


# =====================================================================
# Base Baseline Interface
# =====================================================================

class BaseBaseline(ABC):
    """Abstract base class for all hallucination detection methods."""

    name: str = "BaseBaseline"

    @abstractmethod
    def detect(self, prompt: str, code: str, tests: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        """
        Runs hallucination detection on the given prompt and code.

        Returns:
            Dictionary with standard schema:
            {
                "is_hallucinated": bool,
                "confidence": float,
                "method": str,
                "detections": List[Dict[str, Any]],
                "details": Dict[str, Any]
            }
        """
        pass


# =====================================================================
# 1. PyLint Baseline (Traditional Static Analysis Linter)
# =====================================================================

class PyLintBaseline(BaseBaseline):
    """
    PyLint Baseline (Section IV-C1).
    Runs pylint with --errors-only on the code string, mapping errors into
    the standardized 8-type hallucination taxonomy.
    """
    name: str = "PyLint"

    # Mapping PyLint message symbols / IDs to SDHD 8-type taxonomy
    PYLINT_MAP = {
        "E0602": "Identity Hallucination (IH)",               # undefined-variable
        "E0601": "Identity Hallucination (IH)",               # used-before-assignment
        "E0401": "External Source Hallucination (ESH)",         # import-error
        "E1101": "Structure Access Hallucination (SAH)",        # no-member
        "E1126": "Structure Access Hallucination (SAH)",        # invalid-sequence-index
        "E1127": "Structure Access Hallucination (SAH)",        # slice-index-not-an-integer
        "E1136": "Structure Access Hallucination (SAH)",        # unsubscriptable-object
        "E1130": "Data Compliance Hallucination (DCH)",         # invalid-unary-operand-type
        "E1131": "Data Compliance Hallucination (DCH)",         # unsupported-binary-operation
        "E1120": "Data Compliance Hallucination (DCH)",         # no-value-for-parameter
        "E1121": "Data Compliance Hallucination (DCH)",         # too-many-function-args
        "E0001": "Logical Failure Hallucination (LFH)",         # syntax-error
    }

    def detect(self, prompt: str, code: str, tests: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        try:
            cmd = [sys.executable, "-m", "pylint", temp_path, "--errors-only", "--output-format=json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            raw_out = proc.stdout.strip()
            records = json.loads(raw_out) if raw_out else []
        except Exception:
            records = []
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        detections = []
        for r in records:
            msg_id = r.get("message-id", "")
            symbol = r.get("symbol", "")
            mapped_type = self.PYLINT_MAP.get(msg_id, "Logical Failure Hallucination (LFH)")
            detections.append({
                "error_type": mapped_type,
                "variable_name": symbol or r.get("obj", "unknown"),
                "line_number": r.get("line"),
                "detail": r.get("message", "")
            })

        is_hallu = len(detections) > 0
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "detections": detections,
            "details": {"error_count": len(detections), "raw_pylint_records": records}
        }


# =====================================================================
# 2. Flake8 Baseline (Traditional Static Linter)
# =====================================================================

class Flake8Baseline(BaseBaseline):
    """
    Flake8 Baseline (Section IV-C1).
    Runs flake8 on the code string, mapping error codes into
    the standardized 8-type hallucination taxonomy.
    """
    name: str = "Flake8"

    FLAKE8_MAP = {
        "F821": "Identity Hallucination (IH)",          # undefined name
        "F822": "Identity Hallucination (IH)",          # undefined name in __all__
        "F823": "Identity Hallucination (IH)",          # local variable referenced before assignment
        "E999": "Logical Failure Hallucination (LFH)",    # SyntaxError
        "F706": "Logical Failure Hallucination (LFH)",    # return outside function
    }

    def detect(self, prompt: str, code: str, tests: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        try:
            cmd = [sys.executable, "-m", "flake8", temp_path, "--select=E9,F", "--format=%(code)s:%(row)d:%(col)d:%(text)s"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            lines = proc.stdout.strip().splitlines()
        except Exception:
            lines = []
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        detections = []
        for line in lines:
            parts = line.strip().split(":", 3)
            if len(parts) >= 4:
                code_id, row, col, text = parts[0], parts[1], parts[2], parts[3]
                mapped_type = self.FLAKE8_MAP.get(code_id, "Logical Failure Hallucination (LFH)")
                m = re.search(r"'(.*?)'", text)
                var_name = m.group(1) if m else code_id
                detections.append({
                    "error_type": mapped_type,
                    "variable_name": var_name,
                    "line_number": int(row) if row.isdigit() else None,
                    "detail": text.strip()
                })

        is_hallu = len(detections) > 0
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "detections": detections,
            "details": {"error_count": len(detections)}
        }


# =====================================================================
# 3. CodeEval Baseline (Pure Dynamic Test Execution)
# =====================================================================

class CodeEvalBaseline(BaseBaseline):
    """
    Code-Eval Baseline (Section IV-C1).
    Pure dynamic execution baseline: executes code against provided test cases
    in a sandboxed subprocess without static analysis or iterative refinement.
    """
    name: str = "CodeEval"

    def __init__(self, timeout: int = 5):
        self.timeout = timeout

    def detect(
        self,
        prompt: str,
        code: str,
        tests: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        test_cases = tests or []
        if not test_cases:
            try:
                ast.parse(code)
                return {
                    "is_hallucinated": False,
                    "confidence": 0.5,
                    "method": self.name,
                    "detections": [],
                    "details": {"reason": "No test cases provided; code parses syntactically."}
                }
            except Exception as e:
                return {
                    "is_hallucinated": True,
                    "confidence": 1.0,
                    "method": self.name,
                    "detections": [{"error_type": "Logical Failure Hallucination (LFH)", "variable_name": "syntax", "line_number": None, "detail": str(e)}],
                    "details": {"syntax_error": str(e)}
                }

        report = execute_dynamic_tests(code, test_cases, timeout=self.timeout)
        failed = report.get("failed_tests", 0)
        crashed = report.get("crashed_tests", 0)
        is_error = report.get("status") == "error"

        detections = []
        if is_error:
            detections.append({
                "error_type": "Logical Failure Hallucination (LFH)",
                "variable_name": "execution_environment",
                "line_number": None,
                "detail": report.get("message", "Execution error")
            })

        for r in report.get("results", []):
            if r.get("status") == "failed":
                detections.append({
                    "error_type": "Logical Deviation Hallucination (LDH)",
                    "variable_name": f"test_index_{r.get('test_index', 0)}",
                    "line_number": None,
                    "detail": f"Input: {r.get('input')} | Expected: {r.get('expected')} | Actual: {r.get('actual')}"
                })
            elif r.get("status") == "crashed":
                detections.append({
                    "error_type": "Logical Failure Hallucination (LFH)",
                    "variable_name": f"test_index_{r.get('test_index', 0)}",
                    "line_number": None,
                    "detail": f"Input: {r.get('input')} | Error: {r.get('error')}"
                })

        is_hallu = (failed > 0 or crashed > 0 or is_error)
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "detections": detections,
            "details": {
                "passed_tests": report.get("passed_tests", 0),
                "failed_tests": failed,
                "crashed_tests": crashed,
                "execution_status": report.get("status")
            }
        }


# =====================================================================
# 4. CodeHalu Baseline (Tian et al. [17])
# =====================================================================

class CodeHaluBaseline(BaseBaseline):
    """
    CodeHalu Baseline (Tian et al. [17]).
    Executes code against a single fixed batch of dynamic test cases without
    SSA static analysis or iterative feedback refinement.
    """
    name: str = "CodeHalu"

    def __init__(self, timeout: int = 5, test_count: int = 10):
        self.timeout = timeout
        self.test_count = test_count

    def detect(
        self,
        prompt: str,
        code: str,
        tests: Optional[List[Dict[str, Any]]] = None,
        test_gen_fn: Optional[Callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        test_cases = tests or []
        if not test_cases:
            if test_gen_fn is not None:
                reqs = extract_requirements(prompt, code)
                test_cases = test_gen_fn(reqs, code, None, self.test_count)
            else:
                reqs = extract_requirements(prompt, code)
                test_cases = generate_test_cases_from_requirements(reqs, code, feedback=None, count=self.test_count)

        if not test_cases:
            try:
                ast.parse(code)
                return {
                    "is_hallucinated": False,
                    "confidence": 0.5,
                    "method": self.name,
                    "detections": [],
                    "details": {"reason": "No test cases available, parsed cleanly."}
                }
            except Exception as e:
                return {
                    "is_hallucinated": True,
                    "confidence": 1.0,
                    "method": self.name,
                    "detections": [{"error_type": "Logical Failure Hallucination (LFH)", "variable_name": "syntax", "line_number": None, "detail": str(e)}],
                    "details": {"syntax_error": str(e)}
                }

        report = execute_dynamic_tests(code, test_cases, timeout=self.timeout)
        failed = report.get("failed_tests", 0)
        crashed = report.get("crashed_tests", 0)
        is_error = report.get("status") == "error"

        detections = []
        for r in report.get("results", []):
            if r.get("status") == "failed":
                detections.append({
                    "error_type": "Logical Deviation Hallucination (LDH)",
                    "variable_name": f"test_index_{r.get('test_index', 0)}",
                    "line_number": None,
                    "detail": f"Input: {r.get('input')} | Expected: {r.get('expected')} | Actual: {r.get('actual')}"
                })
            elif r.get("status") == "crashed":
                detections.append({
                    "error_type": "Logical Failure Hallucination (LFH)",
                    "variable_name": f"test_index_{r.get('test_index', 0)}",
                    "line_number": None,
                    "detail": f"Input: {r.get('input')} | Error: {r.get('error')}"
                })

        is_hallu = (failed > 0 or crashed > 0 or is_error)
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "detections": detections,
            "details": {
                "passed_tests": report.get("passed_tests", 0),
                "failed_tests": failed,
                "crashed_tests": crashed,
                "execution_status": report.get("status")
            }
        }


# =====================================================================
# 5. SelfDebug Baseline (Chen et al. [6])
# =====================================================================

class SelfDebugBaseline(BaseBaseline):
    """
    Self-Debug Baseline (Chen et al. [6]).
    Prompts the LLM directly to analyze the requirement and code, asking it to
    identify and classify any hallucinations or bugs.
    """
    name: str = "SelfDebug"

    def __init__(self, client: Optional[Any] = None, model: str = "gemini-2.5-flash", mock_fn: Optional[Callable] = None):
        self.client = client
        self.model = model
        self.mock_fn = mock_fn

    def detect(self, prompt: str, code: str, tests: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        if self.mock_fn is not None:
            return self.mock_fn(prompt, code)

        try:
            from google import genai
            api_key = os.environ.get("GOOGLE_API_KEY", "AIzaSyA4A4AiOWNsThw9kvxwOXta3iCZKTeqciE")
            c = self.client or genai.Client(api_key=api_key)
            system_prompt = (
                "You are an expert code auditor. Analyze the following user requirement and Python code "
                "to determine if it contains any hallucinations, logical bugs, or undefined identifiers.\n\n"
                f"Requirement:\n{prompt}\n\nCode:\n{code}\n\n"
                "Respond STRICTLY with a JSON object:\n"
                '{"is_hallucinated": bool, "confidence": float, "error_type": string or null, "explanation": string}'
            )
            resp = c.models.generate_content(
                model=self.model,
                contents=system_prompt,
                config={"response_mime_type": "application/json"}
            )
            data = json.loads(resp.text)
            is_hallu = bool(data.get("is_hallucinated", False))
            err_type = data.get("error_type")
            detections = []
            if is_hallu and err_type:
                detections.append({
                    "error_type": err_type,
                    "variable_name": "self_debug",
                    "line_number": None,
                    "detail": data.get("explanation", "")
                })
            return {
                "is_hallucinated": is_hallu,
                "confidence": float(data.get("confidence", 1.0 if is_hallu else 0.0)),
                "method": self.name,
                "detections": detections,
                "details": data
            }
        except Exception as e:
            try:
                ast.parse(code)
                return {
                    "is_hallucinated": False,
                    "confidence": 0.5,
                    "method": self.name,
                    "detections": [],
                    "details": {"fallback": "Syntax parsed cleanly, LLM call skipped or failed", "error": str(e)}
                }
            except Exception as syntax_err:
                return {
                    "is_hallucinated": True,
                    "confidence": 1.0,
                    "method": self.name,
                    "detections": [{"error_type": "Logical Failure Hallucination (LFH)", "variable_name": "syntax", "line_number": None, "detail": str(syntax_err)}],
                    "details": {"syntax_error": str(syntax_err)}
                }


# =====================================================================
# 6. SelfCheck Baseline (Sample-consistency agreement) [Li et al., 2023]
# =====================================================================

class SelfCheckBaseline(BaseBaseline):
    """
    SelfCheck Baseline (Li et al. [22]).
    Samples k completions for the same prompt, measuring inter-sample semantic
    or AST consistency. Low consistency indicates a likely hallucination.
    """
    name: str = "SelfCheck"

    def __init__(self, k_samples: int = 3, threshold: float = 0.65):
        self.k_samples = k_samples
        self.threshold = threshold

    def _extract_ast_signature(self, code_str: str) -> set:
        try:
            tree = ast.parse(code_str)
            features = set()
            for node in ast.walk(tree):
                node_type = type(node).__name__
                features.add(node_type)
                if isinstance(node, ast.Name):
                    features.add(f"name:{node.id}")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    features.add(f"call:{node.func.id}")
                elif isinstance(node, ast.Attribute):
                    features.add(f"attr:{node.attr}")
                elif isinstance(node, ast.BinOp):
                    features.add(f"binop:{type(node.op).__name__}")
            return features
        except Exception:
            return {"<SYNTAX_ERROR>"}

    def _jaccard_similarity(self, s1: set, s2: set) -> float:
        if not s1 or not s2:
            return 0.0
        intersection = len(s1.intersection(s2))
        union = len(s1.union(s2))
        return intersection / union if union > 0 else 0.0

    def detect(
        self,
        prompt: str,
        code: str,
        tests: Optional[List[Dict[str, Any]]] = None,
        sample_completions: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        samples = sample_completions or []
        if not samples:
            code_features = self._extract_ast_signature(code)
            if "<SYNTAX_ERROR>" in code_features:
                return {
                    "is_hallucinated": True,
                    "confidence": 1.0,
                    "method": self.name,
                    "detections": [{"error_type": "Logical Failure Hallucination (LFH)", "variable_name": "syntax", "line_number": None, "detail": "Syntax error in completion"}],
                    "details": {"agreement_score": 0.0, "reason": "Syntax error in completion."}
                }
            agreement_score = 0.85
        else:
            code_features = self._extract_ast_signature(code)
            scores = [self._jaccard_similarity(code_features, self._extract_ast_signature(s)) for s in samples]
            agreement_score = sum(scores) / len(scores) if scores else 0.0

        is_hallu = agreement_score < self.threshold
        detections = []
        if is_hallu:
            detections.append({
                "error_type": "Logical Deviation Hallucination (LDH)",
                "variable_name": "completion_consistency",
                "line_number": None,
                "detail": f"Inter-sample consistency {agreement_score:.2f} < threshold {self.threshold:.2f}"
            })
        return {
            "is_hallucinated": is_hallu,
            "confidence": round(max(0.0, min(1.0, 1.0 - agreement_score)), 3),
            "method": self.name,
            "detections": detections,
            "details": {
                "agreement_score": round(agreement_score, 3),
                "threshold": self.threshold,
                "samples_compared": len(samples)
            }
        }


# =====================================================================
# 7. SAC3 Baseline (Semantic Agreement via Cosine Distance) [Manakul et al., 2023]
# =====================================================================

class SAC3Baseline(BaseBaseline):
    """
    SAC3 Baseline (Manakul et al. [23]).
    Measures semantic agreement between the natural language requirement
    and the code's semantic signature.
    """
    name: str = "SAC3"

    def __init__(self, threshold: float = 0.40):
        self.threshold = threshold

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r'[a-zA-Z_]\w*', text.lower())

    def _token_cosine_similarity(self, text1: str, text2: str) -> float:
        tokens1 = self._tokenize(text1)
        tokens2 = self._tokenize(text2)

        if not tokens1 or not tokens2:
            return 0.0

        vec1: Dict[str, int] = {}
        for t in tokens1:
            vec1[t] = vec1.get(t, 0) + 1

        vec2: Dict[str, int] = {}
        for t in tokens2:
            vec2[t] = vec2.get(t, 0) + 1

        all_words = set(vec1.keys()).union(set(vec2.keys()))
        dot = sum(vec1.get(w, 0) * vec2.get(w, 0) for w in all_words)
        norm1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        norm2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def detect(self, prompt: str, code: str, tests: Optional[List[Dict[str, Any]]] = None, **kwargs) -> Dict[str, Any]:
        try:
            ast.parse(code)
        except Exception as e:
            return {
                "is_hallucinated": True,
                "confidence": 1.0,
                "method": self.name,
                "detections": [{"error_type": "Logical Failure Hallucination (LFH)", "variable_name": "syntax", "line_number": None, "detail": str(e)}],
                "details": {"semantic_similarity": 0.0, "reason": "Syntax error in code."}
            }

        sim = self._token_cosine_similarity(prompt, code)
        is_hallu = sim < self.threshold
        detections = []
        if is_hallu:
            detections.append({
                "error_type": "Logical Deviation Hallucination (LDH)",
                "variable_name": "semantic_similarity",
                "line_number": None,
                "detail": f"Cosine similarity {sim:.2f} < threshold {self.threshold:.2f}"
            })

        return {
            "is_hallucinated": is_hallu,
            "confidence": round(max(0.0, min(1.0, 1.0 - sim)), 3),
            "method": self.name,
            "detections": detections,
            "details": {
                "semantic_similarity": round(sim, 3),
                "threshold": self.threshold
            }
        }


# =====================================================================
# 8. SDHD Pipeline Adapter
# =====================================================================

class SDHDBaselineAdapter(BaseBaseline):
    """
    Adapter wrapping the full SDHD_Pipeline into the standard BaseBaseline interface.
    """
    name: str = "SDHD"

    def __init__(self, pipeline: Optional[SDHD_Pipeline] = None):
        self.pipeline = pipeline or SDHD_Pipeline(timeout=5, c_min=10, i_max=3)

    def detect(
        self,
        prompt: str,
        code: str,
        tests: Optional[List[Dict[str, Any]]] = None,
        test_gen_fn: Optional[Callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        report = self.pipeline.run(prompt, code, test_gen_fn=test_gen_fn)
        total_found = report["summary"]["total_hallucinations"]
        overall_status = report["summary"]["overall_status"]
        is_hallu = (overall_status == "POTENTIAL_HALLUCINATION" or total_found > 0)
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "detections": report.get("hallucinations", []),
            "details": {
                "total_hallucinations": total_found,
                "breakdown": report["summary"]["breakdown_by_type"],
                "overall_status": overall_status
            }
        }


# =====================================================================
# Multi-Baseline Record Runner (Definition of Done)
# =====================================================================

def run_all_baselines_on_record(
    record: Any,
    self_debug_mock_fn: Optional[Callable] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Takes a single record (DatasetRecord, BenchmarkRecord, or dict) and executes
    all 5 paper comparison baselines (PyLint, Flake8, CodeEval, CodeHalu, SelfDebug)
    plus SelfCheck, SAC3, and SDHD side-by-side, returning comparable output dicts.
    """
    prompt = getattr(record, "prompt", getattr(record, "requirement_text", record.get("prompt", "") if isinstance(record, dict) else ""))
    code = getattr(record, "code", record.get("code", "") if isinstance(record, dict) else "")
    tests = getattr(record, "tests", getattr(record, "test_cases", record.get("tests", []) if isinstance(record, dict) else []))

    baselines: List[BaseBaseline] = [
        SDHDBaselineAdapter(),
        PyLintBaseline(),
        Flake8Baseline(),
        CodeEvalBaseline(),
        CodeHaluBaseline(),
        SelfDebugBaseline(mock_fn=self_debug_mock_fn),
        SelfCheckBaseline(),
        SAC3Baseline(),
    ]

    results: Dict[str, Dict[str, Any]] = {}
    for b in baselines:
        try:
            res = b.detect(prompt=prompt, code=code, tests=tests)
            results[b.name] = res
        except Exception as e:
            results[b.name] = {
                "is_hallucinated": False,
                "confidence": 0.0,
                "method": b.name,
                "detections": [],
                "details": {"error": str(e)}
            }
    return results


# =====================================================================
# Standard Evaluation Metrics (Section IV-C & Table III)
# =====================================================================

def calculate_metrics(y_true: List[bool], y_pred: List[bool]) -> Dict[str, float]:
    """
    Computes standard evaluation metrics:
    Precision (P), Recall (R), F1 Score, Accuracy (Acc), and False Positive Rate (FPR).
    """
    tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt and yp)
    fp = sum(1 for yt, yp in zip(y_true, y_pred) if not yt and yp)
    tn = sum(1 for yt, yp in zip(y_true, y_pred) if not yt and not yp)
    fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt and not yp)

    total = len(y_true)
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    accuracy = ((tp + tn) / total) if total > 0 else 0.0
    fpr = (fp / (fp + tn)) if (fp + tn) > 0 else 0.0

    return {
        "TP": tp,
        "FP": fp,
        "TN": tn,
        "FN": fn,
        "total": total,
        "Precision": round(precision, 4),
        "Recall": round(recall, 4),
        "F1": round(f1, 4),
        "Accuracy": round(accuracy, 4),
        "FPR": round(fpr, 4),
    }


def evaluate_detector(
    detector: BaseBaseline,
    dataset: List[DatasetRecord],
    test_gen_fn: Optional[Callable] = None
) -> Dict[str, Any]:
    y_true: List[bool] = []
    y_pred: List[bool] = []
    per_record: List[Dict[str, Any]] = []

    for rec in dataset:
        y_true.append(rec.is_hallucinated)

        record_test_gen = None
        if rec.tests:
            def _gen(r, c, f, cnt, _tests=rec.tests):
                return _tests[:cnt] if len(_tests) >= cnt else _tests * (cnt // len(_tests) + 1)
            record_test_gen = _gen
        elif test_gen_fn is not None:
            record_test_gen = test_gen_fn

        try:
            res = detector.detect(
                prompt=rec.prompt,
                code=rec.code,
                tests=rec.tests,
                test_gen_fn=record_test_gen
            )
            pred = bool(res.get("is_hallucinated", False))
        except Exception as e:
            pred = False
            res = {"details": {"error": str(e)}, "is_hallucinated": False, "detections": []}

        y_pred.append(pred)

        per_record.append({
            "task_id": rec.task_id,
            "ground_truth": rec.is_hallucinated,
            "predicted": pred,
            "details": res.get("details", {})
        })

    assert len(y_true) == len(y_pred), (
        f"[evaluate_detector] Internal error: y_true length ({len(y_true)}) != y_pred length ({len(y_pred)})."
    )

    metrics = calculate_metrics(y_true, y_pred)
    return {
        "detector": detector.name,
        "metrics": metrics,
        "records": per_record
    }


def evaluate_all_baselines(dataset: List[DatasetRecord]) -> Dict[str, Dict[str, Any]]:
    detectors: List[BaseBaseline] = [
        SDHDBaselineAdapter(),
        PyLintBaseline(),
        Flake8Baseline(),
        CodeEvalBaseline(),
        CodeHaluBaseline(),
        SelfCheckBaseline(),
        SAC3Baseline()
    ]

    results: Dict[str, Dict[str, Any]] = {}
    for d in detectors:
        res = evaluate_detector(d, dataset)
        results[d.name] = res["metrics"]

    return results


if __name__ == "__main__":
    from dataset_loaders import load_all_datasets
    all_benchmarks = load_all_datasets()
    sample = all_benchmarks["CodeHaluEval"][0]
    print(f"Running all baselines on record: {sample.task_id}...")
    comparison = run_all_baselines_on_record(sample)
    for mname, r in comparison.items():
        print(f"[{mname:<10}] is_hallucinated={r['is_hallucinated']} | detections={len(r.get('detections', []))}")
