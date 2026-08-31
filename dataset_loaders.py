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
    use_online_hf: bool = False
) -> List[DatasetRecord]:
    """
    Loads records from the MBPP dataset (Section IV-A).
    Serves primarily as a verified clean-code pool for measuring false-positive rates (FPR).

    Args:
        split:         Dataset split ("test", "train", "validation").
        n:             Maximum number of records to return.
        clean_only:    If True, guarantees all returned records are labeled clean (is_hallucinated=False).
        use_online_hf: If True, attempts to fetch from Hugging Face before local fallback.

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
            print(f"[DatasetLoader] HF MBPP online load failed ({e}); using bundled local pool.")

    # Local bundled fallback
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

    # BUG-16 FIX: Enforce clean_only after loading — local JSON may contain records where
    # is_hallucinated=True which would silently pollute the clean-code FPR pool.
    if clean_only:
        records = [r for r in records if not r.is_hallucinated]

    if n is not None:
        records = records[:n]

    return records



# =====================================================================
# 2. CodeHaluEval Loader (Dynamic Hallucination Benchmark with Tests)
# =====================================================================

def load_codehalueval(n: Optional[int] = None) -> List[DatasetRecord]:
    """
    Loads records from the CodeHaluEval dataset (Section IV-A, Table II).
    Features 699 tasks with executable test suites (avg 12.8 tests/task)
    and ground-truth hallucination labels (primarily LDH and LFH).

    Args:
        n: Maximum number of records to return.

    Returns:
        List of DatasetRecord instances.
    """
    records: List[DatasetRecord] = []
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
                metadata={"source": "codehalueval"}
            ))

    if n is not None:
        records = records[:n]

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
        records = records[:n]

    return records


# =====================================================================
# Unified Benchmark Loader API
# =====================================================================

def load_all_datasets(
    mbpp_n: Optional[int] = None,
    codehalu_n: Optional[int] = None,
    hallucode_n: Optional[int] = None
) -> Dict[str, List[DatasetRecord]]:
    """
    Loads and aggregates all three paper benchmarks.

    Returns:
        Dictionary mapping dataset name to list of DatasetRecord instances.
    """
    return {
        "MBPP": load_mbpp(n=mbpp_n, clean_only=True),
        "CodeHaluEval": load_codehalueval(n=codehalu_n),
        "HalluCode": load_hallucode(n=hallucode_n),
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
        total_tests = sum(len(r.tests) for r in records)
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
