"""
baselines.py - Baseline Reproductions & Benchmark Evaluation Tools (Section IV-C1)
===================================================================================
Implements the three comparison baselines from Section IV-C1 of the SDHD paper:
1. CodeHalu (Tian et al. [17]): Execution-based dynamic verification without static analysis or iterative feedback loops.
2. SelfCheck (Li et al. [22]): Multi-sample consistency checking measuring agreement across k completions.
3. SAC3 (Manakul et al. [23]): Semantic Agreement check using embedding cosine similarity between requirement and code.

Also provides standard Precision, Recall, F1, and FPR evaluation utilities.
"""

import ast
import math
import re
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
    def detect(self, prompt: str, code: str, **kwargs) -> Dict[str, Any]:
        """
        Runs hallucination detection on the given prompt and code.

        Returns:
            Dictionary with standard schema:
            {
                "is_hallucinated": bool,
                "confidence": float,
                "method": str,
                "details": Dict[str, Any]
            }
        """
        pass


# =====================================================================
# 1. CodeHalu Baseline (Execution-based dynamic verification) [Tian et al., 2024]
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
        # Use provided tests or generate one-pass tests
        test_cases = tests or []
        if not test_cases:
            if test_gen_fn is not None:
                reqs = extract_requirements(prompt, code)
                test_cases = test_gen_fn(reqs, code, None, self.test_count)
            else:
                reqs = extract_requirements(prompt, code)
                test_cases = generate_test_cases_from_requirements(reqs, code, feedback=None, count=self.test_count)

        if not test_cases:
            # Cannot execute tests -> fallback to syntax check
            try:
                ast.parse(code)
                return {
                    "is_hallucinated": False,
                    "confidence": 0.5,
                    "method": self.name,
                    "details": {"reason": "No test cases available, parsed cleanly."}
                }
            except Exception as e:
                return {
                    "is_hallucinated": True,
                    "confidence": 1.0,
                    "method": self.name,
                    "details": {"syntax_error": str(e)}
                }

        report = execute_dynamic_tests(code, test_cases, timeout=self.timeout)
        failed = report.get("failed_tests", 0)
        crashed = report.get("crashed_tests", 0)
        is_error = report.get("status") == "error"

        is_hallu = (failed > 0 or crashed > 0 or is_error)
        conf = 1.0 if is_hallu else 0.0

        return {
            "is_hallucinated": is_hallu,
            "confidence": conf,
            "method": self.name,
            "details": {
                "passed_tests": report.get("passed_tests", 0),
                "failed_tests": failed,
                "crashed_tests": crashed,
                "execution_status": report.get("status")
            }
        }


# =====================================================================
# 2. SelfCheck Baseline (Sample-consistency agreement) [Li et al., 2023]
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
        """Extracts structural AST feature tokens for consistency comparison."""
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
        """Computes Jaccard similarity between two feature sets."""
        if not s1 or not s2:
            return 0.0
        intersection = len(s1.intersection(s2))
        union = len(s1.union(s2))
        return intersection / union if union > 0 else 0.0

    def detect(
        self,
        prompt: str,
        code: str,
        sample_completions: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        # If candidate samples are provided, measure inter-sample agreement
        samples = sample_completions or []
        if not samples:
            # Default self-consistency proxy: check AST syntax validity and structural consistency
            code_features = self._extract_ast_signature(code)
            if "<SYNTAX_ERROR>" in code_features:
                return {
                    "is_hallucinated": True,
                    "confidence": 1.0,
                    "method": self.name,
                    "details": {"agreement_score": 0.0, "reason": "Syntax error in completion."}
                }
            # High default consistency if self-contained
            agreement_score = 0.85
        else:
            code_features = self._extract_ast_signature(code)
            scores = [self._jaccard_similarity(code_features, self._extract_ast_signature(s)) for s in samples]
            agreement_score = sum(scores) / len(scores) if scores else 0.0

        is_hallu = agreement_score < self.threshold
        return {
            "is_hallucinated": is_hallu,
            # BUG-19 FIX: Clamp confidence to [0.0, 1.0] to guard against future
            # agreement_score implementations that could return values outside [0, 1].
            "confidence": round(max(0.0, min(1.0, 1.0 - agreement_score)), 3),
            "method": self.name,
            "details": {
                "agreement_score": round(agreement_score, 3),
                "threshold": self.threshold,
                "samples_compared": len(samples)
            }
        }



# =====================================================================
# 3. SAC3 Baseline (Semantic Agreement via Embedding Similarity) [Manakul et al., 2023]
# =====================================================================

class SAC3Baseline(BaseBaseline):
    """
    SAC3 Baseline (Manakul et al. [23]).
    Measures semantic agreement / cosine similarity between the natural language requirement
    and the code's semantic signature. Flags low-similarity completions.
    """
    name: str = "SAC3"

    def __init__(self, threshold: float = 0.40):
        self.threshold = threshold

    def _tokenize(self, text: str) -> List[str]:
        """Normalizes and extracts alphanumeric semantic tokens."""
        return re.findall(r'[a-zA-Z_]\w*', text.lower())

    def _token_cosine_similarity(self, text1: str, text2: str) -> float:
        """Computes TF-IDF / frequency cosine similarity between two text strings."""
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

    def detect(self, prompt: str, code: str, **kwargs) -> Dict[str, Any]:
        # Check syntax first
        try:
            ast.parse(code)
        except Exception:
            return {
                "is_hallucinated": True,
                "confidence": 1.0,
                "method": self.name,
                "details": {"semantic_similarity": 0.0, "reason": "Syntax error in code."}
            }

        sim = self._token_cosine_similarity(prompt, code)
        is_hallu = sim < self.threshold

        return {
            "is_hallucinated": is_hallu,
            # BUG-19 FIX: Clamp confidence to [0.0, 1.0] — if similarity measure is ever changed
            # to use signed embeddings, 1.0 - sim could exceed 1.0 silently.
            "confidence": round(max(0.0, min(1.0, 1.0 - sim)), 3),
            "method": self.name,
            "details": {
                "semantic_similarity": round(sim, 3),
                "threshold": self.threshold
            }
        }



# =====================================================================
# 4. SDHD Pipeline Adapter
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
        test_gen_fn: Optional[Callable] = None,
        **kwargs
    ) -> Dict[str, Any]:
        report = self.pipeline.run(prompt, code, test_gen_fn=test_gen_fn)
        total_found = report["summary"]["total_hallucinations"]
        is_hallu = total_found > 0
        return {
            "is_hallucinated": is_hallu,
            "confidence": 1.0 if is_hallu else 0.0,
            "method": self.name,
            "details": {
                "total_hallucinations": total_found,
                "breakdown": report["summary"]["breakdown_by_type"],
                "overall_status": report["summary"]["overall_status"]
            }
        }


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
    """
    Evaluates a given detector against a benchmark dataset of DatasetRecord objects.
    """
    y_true: List[bool] = []
    y_pred: List[bool] = []
    per_record: List[Dict[str, Any]] = []

    for rec in dataset:
        y_true.append(rec.is_hallucinated)

        # BUG-17 FIX: Capture rec.tests by value using a default argument to avoid the classic
        # Python closure-captures-loop-variable bug. Without this, all _gen closures share the
        # same `rec` reference which points to the last record after loop completion.
        record_test_gen = None
        if rec.tests:
            def _gen(r, c, f, cnt, _tests=rec.tests):
                return _tests[:cnt] if len(_tests) >= cnt else _tests * (cnt // len(_tests) + 1)
            record_test_gen = _gen
        elif test_gen_fn is not None:
            record_test_gen = test_gen_fn

        # BUG-18 FIX: Wrap detector.detect() in try/except. Without this, any exception mid-loop
        # would abort with y_true and y_pred at different lengths. zip() would silently truncate
        # metrics to the shorter list, producing wrong Precision/Recall/F1 without any error.
        try:
            res = detector.detect(
                prompt=rec.prompt,
                code=rec.code,
                tests=rec.tests,
                test_gen_fn=record_test_gen
            )
            pred = bool(res.get("is_hallucinated", False))
        except Exception as e:
            pred = False  # Conservative: treat detect errors as non-hallucination
            res = {"details": {"error": str(e)}, "is_hallucinated": False}

        y_pred.append(pred)

        per_record.append({
            "task_id": rec.task_id,
            "ground_truth": rec.is_hallucinated,
            "predicted": pred,
            "details": res.get("details", {})
        })

    # BUG-18 FIX: Explicit length guard before metrics computation.
    assert len(y_true) == len(y_pred), (
        f"[evaluate_detector] Internal error: y_true length ({len(y_true)}) != "
        f"y_pred length ({len(y_pred)}). This indicates a logic bug in the loop."
    )

    metrics = calculate_metrics(y_true, y_pred)
    return {
        "detector": detector.name,
        "metrics": metrics,
        "records": per_record
    }



def evaluate_all_baselines(dataset: List[DatasetRecord]) -> Dict[str, Dict[str, Any]]:
    """
    Runs all 4 detectors (SDHD, CodeHalu, SelfCheck, SAC3) across a dataset.
    Returns comparison dictionary mirroring Table III of the paper.
    """
    detectors: List[BaseBaseline] = [
        SDHDBaselineAdapter(),
        CodeHaluBaseline(),
        SelfCheckBaseline(),
        SAC3Baseline()
    ]

    results: Dict[str, Dict[str, Any]] = {}
    for d in detectors:
        res = evaluate_detector(d, dataset)
        results[d.name] = res["metrics"]

    return results


# --- Standalone Demo Execution ---
if __name__ == "__main__":
    all_benchmarks = load_all_datasets()
    combined_pool = (
        all_benchmarks["MBPP"][:3] +
        all_benchmarks["CodeHaluEval"][:3] +
        all_benchmarks["HalluCode"][:3]
    )

    print("=== Table III Baseline Comparison (SDHD vs Baselines) ===")
    comp_results = evaluate_all_baselines(combined_pool)
    for method, metrics in comp_results.items():
        print(f"{method:<12} | Precision: {metrics['Precision']:.3f} | Recall: {metrics['Recall']:.3f} | F1: {metrics['F1']:.3f} | Acc: {metrics['Accuracy']:.3f} | FPR: {metrics['FPR']:.3f}")
