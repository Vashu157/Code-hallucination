"""
dataset_loaders.py - Unified Multi-Benchmark Dataset Loaders (Section IV-A, Table II)
=====================================================================================
Integrates the three benchmark datasets from the SDHD paper:
1. MBPP (Mostly Basic Python Problems): 974 tasks, manual, avg 3.0 tests/task (Clean code pool & FPR testing)
2. CodeHaluEval: 699 tasks, automated dynamic tests, avg 12.8 tests/task (LDH, LFH annotations)
3. HalluCode: 5664 tasks, automated+manual, no executable tests (DCH, SAH, IH, ESH, PCH, CBH annotations)

All loaders return uniform `DatasetRecord` objects.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


@dataclass
class DatasetRecord:
    """
    Uniform schema representing a benchmark task across MBPP, CodeHaluEval, and HalluCode.
    """
    task_id: Union[str, int]
    dataset: str  # "MBPP" | "CodeHaluEval" | "HalluCode"
    prompt: str
    code: str
    clean_code: Optional[str] = None
    tests: List[Dict[str, Any]] = field(default_factory=list)
    ground_truth_labels: List[Dict[str, Any]] = field(default_factory=list)
    is_hallucinated: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes DatasetRecord to dictionary."""
        return {
            "task_id": self.task_id,
            "dataset": self.dataset,
            "prompt": self.prompt,
            "code": self.code,
            "clean_code": self.clean_code,
            "tests": self.tests,
            "ground_truth_labels": self.ground_truth_labels,
            "is_hallucinated": self.is_hallucinated,
            "metadata": self.metadata,
        }


# =====================================================================
# 1. MBPP Loader (Clean-Code Pool + Optional Synthetic Mutation Target)
# =====================================================================

def load_mbpp(
    split: str = "test",
    n: Optional[int] = None,
    clean_only: bool = True,
    use_online_hf: bool = False,
    use_full: bool = False
) -> List[DatasetRecord]:
    """
    Loads records from the MBPP dataset (Section IV-A).
    Serves primarily as a verified clean-code pool for measuring false-positive rates (FPR).

    Args:
        split:         Dataset split ("test", "train", "validation").
        n:             Maximum number of records to return.
        clean_only:    If True, guarantees all returned records are labeled clean (is_hallucinated=False).
        use_online_hf: If True, attempts to fetch from Hugging Face before local fallback.
        use_full:      If True, loads from the full 974-task release (data/mbpp.jsonl).

    Returns:
        List of DatasetRecord instances.
    """
    records: List[DatasetRecord] = []

    # Attempt online loading if requested
    if use_online_hf:
        try:
            from datasets import load_dataset
            ds = load_dataset("mbpp", split=split)
            limit = n if n is not None else len(ds)
            for i in range(min(limit, len(ds))):
                item = ds[i]
                test_list = item.get("test_list", [])
                formatted_tests = [{"assertion": t} for t in test_list]
                records.append(DatasetRecord(
                    task_id=item.get("task_id", i),
                    dataset="MBPP",
                    prompt=item.get("text", ""),
                    code=item.get("code", ""),
                    clean_code=item.get("code", ""),
                    tests=formatted_tests,
                    ground_truth_labels=[],
                    is_hallucinated=False,
                    metadata={"source": "huggingface_mbpp", "split": split}
                ))
            return records
        except Exception as e:
            print(f"[DatasetLoader] HF MBPP online load failed ({e}); using local files.")

    # 1. Full 974-task MBPP release from Google Research
    full_mbpp_path = os.path.join(DATA_DIR, "mbpp.jsonl")
    if use_full and os.path.exists(full_mbpp_path):
        with open(full_mbpp_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                test_list = item.get("test_list", [])
                formatted_tests = [{"assertion": t} for t in test_list]
                records.append(DatasetRecord(
                    task_id=item.get("task_id"),
                    dataset="MBPP",
                    prompt=item.get("text", ""),
                    code=item.get("code", ""),
                    clean_code=item.get("code", ""),
                    tests=formatted_tests,
                    ground_truth_labels=[],
                    is_hallucinated=False,
                    metadata={"source": "google_research_mbpp_full", "setup_code": item.get("test_setup_code", "")}
                ))
    else:
        # 2. Local bundled sample fallback
        local_path = os.path.join(DATA_DIR, "mbpp_clean.json")
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            for item in raw_data:
                records.append(DatasetRecord(
                    task_id=item.get("task_id"),
                    dataset="MBPP",
                    prompt=item.get("prompt", ""),
                    code=item.get("code", ""),
                    clean_code=item.get("clean_code", item.get("code", "")),
                    tests=item.get("tests", []),
                    ground_truth_labels=item.get("ground_truth_labels", []),
                    is_hallucinated=item.get("is_hallucinated", False),
                    metadata={"source": "local_mbpp_clean"}
                ))

    # Enforce clean_only after loading
    if clean_only:
        records = [r for r in records if not r.is_hallucinated]

    if n is not None:
        records = records[:max(0, n)]

    return records


# =====================================================================
# 2. CodeHaluEval Loader (Dynamic Hallucination Benchmark with Tests)
# =====================================================================

CHE_CATEGORY_MAP = {
    "data_compliance_hallucination.json": ("DCH", "Data Compliance Hallucination (DCH)"),
    "structural_access_hallucination.json": ("SAH", "Structure Access Hallucination (SAH)"),
    "identification_hallucination.json": ("IH", "Identity Hallucination (IH)"),
    "external_source_hallucination.json": ("ESH", "External Source Hallucination (ESH)"),
    "physical_constraint_hallucination.json": ("PCH", "Physical Constraint Hallucination (PCH)"),
    "calculate_boundary_hallucination.json": ("CBH", "Computational Boundary Hallucination (CBH)"),
    "logic_deviation.json": ("LDH", "Logical Deviation Hallucination (LDH)"),
    "logic_breakdown.json": ("LFH", "Logical Failure Hallucination (LFH)"),
}


def load_codehalueval(
    n: Optional[int] = None,
    use_full: bool = False,
    per_category_limit: Optional[int] = None,
    categories: Optional[List[str]] = None
) -> List[DatasetRecord]:
    """
    Loads records from the CodeHaluEval dataset (Section IV-A, Table II).
    Features executable test suites and ground-truth hallucination labels across all 8 canonical types.

    Args:
        n:                  Maximum total number of records to return.
        use_full:           If True, loads directly from downloaded data/codehalueval/ category files.
        per_category_limit: Maximum records to pull per canonical category.
        categories:         Optional list of specific filenames or type_codes to load.

    Returns:
        List of DatasetRecord instances.
    """
    records: List[DatasetRecord] = []
    che_dir = os.path.join(DATA_DIR, "codehalueval")

    if use_full and os.path.exists(che_dir):
        for fname, (tcode, tname) in CHE_CATEGORY_MAP.items():
            if categories and (fname not in categories and tcode not in categories):
                continue
            fpath = os.path.join(che_dir, fname)
            if not os.path.exists(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                cat_count = 0
                for item in data:
                    sol = item.get("solutions")
                    if not sol:
                        continue
                    if isinstance(sol, str):
                        try:
                            sol = json.loads(sol)
                        except Exception:
                            sol = [sol]
                    code = sol[0] if sol else ""
                    if not code or not code.strip():
                        continue

                    inp = item.get("input", "")
                    out = item.get("output", "")
                    tests = [{"input": inp, "expected_output": out}] if inp else []

                    tid = str(item.get("task_id", cat_count))
                    records.append(DatasetRecord(
                        task_id=f"{tcode}_{tid}",
                        dataset="CodeHaluEval",
                        prompt=item.get("question", ""),
                        code=code,
                        clean_code=None,
                        tests=tests,
                        ground_truth_labels=[{"type_code": tcode, "error_type": tname}],
                        is_hallucinated=True,
                        metadata={
                            "source": "codehalueval_hf",
                            "category_file": fname,
                            "type_code": tcode,
                            "fn_name": item.get("fn_name"),
                            "difficulty": item.get("difficulty")
                        }
                    ))
                    cat_count += 1
                    if per_category_limit and cat_count >= per_category_limit:
                        break
            except Exception as e:
                print(f"[DatasetLoader] Error loading {fname}: {e}")

    else:
        # Bundled sample fallback
        local_path = os.path.join(DATA_DIR, "codehalueval_samples.json")
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            for item in raw_data:
                records.append(DatasetRecord(
                    task_id=item.get("task_id"),
                    dataset="CodeHaluEval",
                    prompt=item.get("prompt", ""),
                    code=item.get("code", ""),
                    clean_code=item.get("clean_code"),
                    tests=item.get("tests", []),
                    ground_truth_labels=item.get("ground_truth_labels", []),
                    is_hallucinated=item.get("is_hallucinated", True),
                    metadata={"source": "codehalueval_samples"}
                ))

    if n is not None:
        records = records[:max(0, n)]

    return records


# =====================================================================
# 3. HalluCode Loader (Static Hallucination Benchmark without Tests)
# =====================================================================

def load_hallucode(n: Optional[int] = None) -> List[DatasetRecord]:
    """
    Loads records from the HalluCode dataset (Section IV-A, Table II).
    Features 5,664 tasks with annotated static hallucination categories
    (DCH, SAH, IH, ESH, PCH, CBH) and no executable test suites (Test = N/A).

    Args:
        n: Maximum number of records to return.

    Returns:
        List of DatasetRecord instances.
    """
    records: List[DatasetRecord] = []
    local_path = os.path.join(DATA_DIR, "hallucode_samples.json")

    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        for item in raw_data:
            records.append(DatasetRecord(
                task_id=item.get("task_id"),
                dataset="HalluCode",
                prompt=item.get("prompt", ""),
                code=item.get("code", ""),
                clean_code=item.get("clean_code"),
                tests=[],  # HalluCode has Test = N/A per Table II
                ground_truth_labels=item.get("ground_truth_labels", []),
                is_hallucinated=item.get("is_hallucinated", True),
                metadata={"source": "hallucode"}
            ))

    if n is not None:
        records = records[:max(0, n)]

    return records


# =====================================================================
# 4. EvalPlus Loader (Empirical Ground-Truth from Real Pre-Generated LLM Code)
# =====================================================================

def load_evalplus(
    dataset: str = "humaneval",
    model: str = "chatgpt",
    n: Optional[int] = None,
    clean_only: bool = False,
    hallucinated_only: bool = False,
    auto_fetch: bool = True
) -> List[DatasetRecord]:
    """
    Loads empirical benchmark records from EvalPlus pre-generated LLM completions.
    Pass/fail ground-truth is established directly by EvalPlus's execution engine
    against base+plus oracle test suites.

    Args:
        dataset: "humaneval" or "mbpp".
        model: Model alias (e.g. "chatgpt", "starcoder", "gpt-3.5-turbo", "gpt-4").
        n: Maximum number of records to return.
        clean_only: Return only non-hallucinated (passed all tests) records.
        hallucinated_only: Return only hallucinated (failed tests) records.
        auto_fetch: If True and records JSON does not exist, downloads and evaluates via evalplus_fetcher.

    Returns:
        List of DatasetRecord instances.
    """
    norm_ds = "mbpp" if "mbpp" in dataset.lower() else "humaneval"
    evalplus_dir = os.path.join(DATA_DIR, "evalplus")
    os.makedirs(evalplus_dir, exist_ok=True)
    records_file = os.path.join(evalplus_dir, f"{norm_ds}_{model}_records.json")

    records: List[DatasetRecord] = []
    if os.path.exists(records_file):
        from evalplus_fetcher import load_dataset_records_from_file
        records = load_dataset_records_from_file(records_file)
    elif auto_fetch:
        from evalplus_fetcher import fetch_and_evaluate_evalplus
        records = fetch_and_evaluate_evalplus(
            dataset=norm_ds,
            model=model,
            limit=n,
            save_path=records_file,
            verbose=False
        )

    if clean_only:
        records = [r for r in records if not r.is_hallucinated]
    elif hallucinated_only:
        records = [r for r in records if r.is_hallucinated]

    if n is not None:
        records = records[:max(0, n)]

    return records


# =====================================================================
# Unified Benchmark Loader API
# =====================================================================

def load_all_datasets(
    mbpp_n: Optional[int] = None,
    codehalu_n: Optional[int] = None,
    hallucode_n: Optional[int] = None,
    use_full: bool = False
) -> Dict[str, List[DatasetRecord]]:
    """
    Loads benchmark datasets.

    Args:
        mbpp_n: Maximum MBPP records to load.
        codehalu_n: Maximum CodeHaluEval records to load.
        hallucode_n: Maximum HalluCode records to load.
        use_full: If True, loads from real downloaded datasets (mbpp.jsonl and data/codehalueval/*.json).
                  If False, loads local unit test fixtures (22 tasks for fast CI test suite).

    Returns:
        Dictionary mapping dataset name to list of DatasetRecord instances.
    """
    return {
        "MBPP": load_mbpp(n=mbpp_n, clean_only=True, use_full=use_full),
        "CodeHaluEval": load_codehalueval(n=codehalu_n, use_full=use_full),
        "HalluCode": load_hallucode(n=hallucode_n),
    }


def load_real_benchmarks(
    mbpp_n: int = 100,
    che_per_category: int = 25
) -> Dict[str, List[DatasetRecord]]:
    """
    Loads genuine real-world benchmark tasks from downloaded sources:
    - MBPP: Google Research release (mbpp.jsonl) - clean-code pool
    - CodeHaluEval: Hugging Face release (data/codehalueval/) across all 8 canonical types
    - HalluCode: Marked as unreleased author artifact (author contacted via email)
    """
    return {
        "MBPP": load_mbpp(n=mbpp_n, clean_only=True, use_full=True),
        "CodeHaluEval": load_codehalueval(use_full=True, per_category_limit=che_per_category),
        "HalluCode": load_hallucode()
    }


def get_dataset_summary(datasets_dict: Dict[str, List[DatasetRecord]]) -> Dict[str, Any]:
    """
    Generates a structured summary table mirroring Table II of the base paper.
    """
    summary: Dict[str, Any] = {}
    for name, records in datasets_dict.items():
        total_tasks = len(records)
        hallucinated_count = sum(1 for r in records if r.is_hallucinated)
        clean_count = sum(1 for r in records if not r.is_hallucinated)
        total_tests = sum(len(r.tests or []) for r in records)
        avg_tests = (total_tests / total_tasks) if total_tasks > 0 else 0.0

        label_counts: Dict[str, int] = {}
        for r in records:
            for label in r.ground_truth_labels:
                tcode = label.get("type_code", "UNKNOWN")
                label_counts[tcode] = label_counts.get(tcode, 0) + 1

        summary[name] = {
            "total_tasks": total_tasks,
            "clean_tasks": clean_count,
            "hallucinated_tasks": hallucinated_count,
            "total_test_cases": total_tests,
            "avg_tests_per_task": round(avg_tests, 2),
            "annotated_type_breakdown": label_counts,
        }
    return summary


# --- Example Standalone Usage ---
if __name__ == "__main__":
    all_data = load_all_datasets()
    summary_report = get_dataset_summary(all_data)
    print("=== Table II Benchmark Dataset Summary ===")
    print(json.dumps(summary_report, indent=2))
