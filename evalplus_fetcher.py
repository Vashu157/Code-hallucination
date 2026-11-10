"""
evalplus_fetcher.py - Automated EvalPlus Pre-Generated Sample Fetcher & Evaluator
==================================================================================
Pulls existing pre-generated LLM completions from EvalPlus GitHub releases,
runs them through EvalPlus's own execution sandbox & oracle evaluator to obtain
unambiguous pass/fail ground truth, and converts them into the canonical `DatasetRecord` format.

Zero LLM API calls required - leverages pre-existing benchmark generations and
EvalPlus's rigorous base+plus test suites.
"""

import argparse
import contextlib
import json
import multiprocessing
import os
import sys
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure Windows compatibility environment variables are set before evalplus imports
os.environ["EVALPLUS_MAX_MEMORY_BYTES"] = "-1"


# =====================================================================
# 1. Windows Compatibility & Platform Sandbox Patching
# =====================================================================

@contextlib.contextmanager
def safe_time_limit(seconds: float):
    """
    Cross-platform no-op / safe context manager for per-input execution timeouts.
    On Unix, signal.setitimer can be used; on Windows, signal.setitimer does not exist.
    The outer process-level timeout (via Process.join(timeout)) already bounds execution safely.
    """
    yield


def apply_windows_patches() -> None:
    """
    Applies runtime compatibility monkeypatches for Windows environments:
    - Patches evalplus.eval.utils.time_limit (replaces Unix signal.setitimer with safe_time_limit).
    - Sets EVALPLUS_MAX_MEMORY_BYTES to -1 to disable Unix-specific resource.setrlimit.
    """
    os.environ["EVALPLUS_MAX_MEMORY_BYTES"] = "-1"
    try:
        import evalplus.eval.utils as eu
        eu.time_limit = safe_time_limit
    except ImportError:
        pass

    try:
        import evalplus.eval as ee
        ee.time_limit = safe_time_limit
    except (ImportError, AttributeError):
        pass


# Apply patches immediately on module import
apply_windows_patches()


# =====================================================================
# 2. Pre-Generated Release Model Registry
# =====================================================================

DEFAULT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "evalplus_cache"
)

# EvalPlus GitHub Release URLs
EVALPLUS_RELEASE_BASE_V010 = "https://github.com/evalplus/evalplus/releases/download/v0.1.0"
EVALPLUS_RELEASE_BASE_V020 = "https://github.com/evalplus/evalplus/releases/download/v0.2.0"

EVALPLUS_MODELS = {
    "humaneval": {
        "chatgpt": f"{EVALPLUS_RELEASE_BASE_V010}/chatgpt_temp_0.0.zip",
        "chatgpt_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V010}/chatgpt_temp_0.0.zip",
        "starcoder": f"{EVALPLUS_RELEASE_BASE_V010}/starcoder_temp_0.0.zip",
        "starcoder_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V010}/starcoder_temp_0.0.zip",
        "code-llama-7b": f"{EVALPLUS_RELEASE_BASE_V010}/code-llama-7b_temp_0.0.zip",
        "code-llama-7b_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V010}/code-llama-7b_temp_0.0.zip",
        "vicuna-7b": f"{EVALPLUS_RELEASE_BASE_V010}/vicuna-7b_temp_0.0.zip",
        "vicuna-7b_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V010}/vicuna-7b_temp_0.0.zip",
        "wizardcoder-7b": f"{EVALPLUS_RELEASE_BASE_V010}/wizardcoder-7b_temp_0.0.zip",
        "wizardcoder-7b_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V010}/wizardcoder-7b_temp_0.0.zip",
    },
    "mbpp": {
        "gpt-3.5-turbo": f"{EVALPLUS_RELEASE_BASE_V020}/gpt-3.5-turbo_temp_0.0.zip",
        "gpt-3.5-turbo_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V020}/gpt-3.5-turbo_temp_0.0.zip",
        "gpt-4": f"{EVALPLUS_RELEASE_BASE_V020}/gpt-4-1106-preview_temp_0.0.zip",
        "gpt-4-1106-preview": f"{EVALPLUS_RELEASE_BASE_V020}/gpt-4-1106-preview_temp_0.0.zip",
        "gpt-4-1106-preview_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V020}/gpt-4-1106-preview_temp_0.0.zip",
        "deepseek-coder": f"{EVALPLUS_RELEASE_BASE_V020}/deepseek-coder-6.7b-instruct_temp_0.0.zip",
        "deepseek-coder-6.7b-instruct_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V020}/deepseek-coder-6.7b-instruct_temp_0.0.zip",
        "starcoder": f"{EVALPLUS_RELEASE_BASE_V020}/starcoder_temp_0.0.zip",
        "starcoder_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V020}/starcoder_temp_0.0.zip",
        "mistral-7b": f"{EVALPLUS_RELEASE_BASE_V020}/mistral-7b_temp_0.0.zip",
        "mistral-7b_temp_0.0": f"{EVALPLUS_RELEASE_BASE_V020}/mistral-7b_temp_0.0.zip",
    }
}


def get_model_download_url(dataset: str, model: str) -> str:
    """Returns the release zip download URL for a given dataset and model alias."""
    norm_ds = dataset.lower().replace("-", "").replace("_", "")
    if "humaneval" in norm_ds:
        ds_key = "humaneval"
    elif "mbpp" in norm_ds:
        ds_key = "mbpp"
    else:
        raise ValueError(f"Unknown dataset '{dataset}'. Must be 'humaneval' or 'mbpp'.")

    models_map = EVALPLUS_MODELS[ds_key]
    if model in models_map:
        return models_map[model]
    norm_m = model.lower()
    for k, url in models_map.items():
        if norm_m == k.lower():
            return url

    raise ValueError(
        f"Unknown model '{model}' for dataset '{dataset}'. "
        f"Available models: {list(models_map.keys())}"
    )


# =====================================================================
# 3. Sample Fetcher & Extractor
# =====================================================================

def fetch_evalplus_samples(
    dataset: str = "humaneval",
    model: str = "chatgpt",
    cache_dir: Optional[str] = None
) -> str:
    """
    Downloads and extracts pre-generated LLM completions from EvalPlus GitHub releases.

    Args:
        dataset:   "humaneval" or "mbpp".
        model:     Model name or alias (e.g. "chatgpt", "gpt-3.5-turbo", "starcoder").
        cache_dir: Optional cache directory path (defaults to data/evalplus_cache/).

    Returns:
        Absolute path to the extracted completions directory containing task folders.
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)

    url = get_model_download_url(dataset, model)
    zip_filename = os.path.basename(url)
    zip_path = os.path.join(cache_dir, zip_filename)

    # 1. Download zip if not already present
    if not os.path.exists(zip_path) or os.path.getsize(zip_path) == 0:
        print(f"[EvalPlusFetcher] Downloading {url} -> {zip_path}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out_f:
            out_f.write(resp.read())
        print(f"[EvalPlusFetcher] Downloaded {os.path.getsize(zip_path)} bytes.")

    # 2. Extract zip
    extract_target_dir = os.path.join(cache_dir, "extracted", zip_filename.replace(".zip", ""))
    os.makedirs(extract_target_dir, exist_ok=True)

    # Check if already extracted
    need_extract = True
    for root, dirs, files in os.walk(extract_target_dir):
        if any(f.endswith(".py") for f in files):
            need_extract = False
            break

    if need_extract:
        print(f"[EvalPlusFetcher] Extracting {zip_path} -> {extract_target_dir}...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_target_dir)

    # 3. Locate the leaf directory containing task subfolders (e.g. HumanEval_0 or Mbpp_11)
    for root, dirs, files in os.walk(extract_target_dir):
        # A task directory typically has names like HumanEval_X or Mbpp_X and contains 0.py
        has_task_subdirs = any(
            d.startswith("HumanEval") or d.startswith("Mbpp") or d.startswith("HumanEval_") or d.startswith("Mbpp_")
            for d in dirs
        )
        if has_task_subdirs:
            return root

    # Fallback to extract target dir
    return extract_target_dir


# =====================================================================
# 4. Evaluator & Ground Truth Engine
# =====================================================================

def get_or_compute_task_groundtruth(
    problem: Dict[str, Any],
    dataset: str,
    cached_groundtruth: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Retrieves or computes ground-truth oracle outputs for a single problem.
    Uses trusted_exec to calculate expected base and plus outputs.
    """
    task_id = problem["task_id"]
    if cached_groundtruth and task_id in cached_groundtruth:
        return cached_groundtruth[task_id]

    from evalplus.evaluate import trusted_exec, MBPP_OUTPUT_NOT_NONE_TASKS

    is_mbpp = "mbpp" in dataset.lower()
    entry_point = problem["entry_point"]
    output_not_none = entry_point in MBPP_OUTPUT_NOT_NONE_TASKS if is_mbpp else False

    base_out, base_time = trusted_exec(
        problem["prompt"] + problem["canonical_solution"],
        problem["base_input"],
        entry_point,
        record_time=True,
        output_not_none=output_not_none,
    )
    plus_out, plus_time = trusted_exec(
        problem["prompt"] + problem["canonical_solution"],
        problem["plus_input"],
        entry_point,
        record_time=True,
        output_not_none=output_not_none,
    )

    return {
        "base": base_out,
        "base_time": base_time,
        "plus": plus_out,
        "plus_time": plus_time,
    }


def evaluate_single_sample(
    problem: Dict[str, Any],
    solution_code: str,
    dataset: str = "humaneval",
    expected_output: Optional[Dict[str, Any]] = None,
    base_only: bool = False,
    fast_check: bool = True
) -> Dict[str, Any]:
    """
    Executes a single solution in the EvalPlus sandbox against base and plus test suites.

    Returns:
        Dict with keys:
            - base_status: "pass" | "fail" | "timeout"
            - plus_status: "pass" | "fail" | "timeout" | None
            - is_hallucinated: bool (True if either base or plus failed)
            - base_details: List[bool]
            - plus_details: List[bool]
    """
    apply_windows_patches()
    from evalplus.evaluate import check_correctness

    if expected_output is None:
        expected_output = get_or_compute_task_groundtruth(problem, dataset)

    norm_ds = "mbpp" if "mbpp" in dataset.lower() else "humaneval"

    res = check_correctness(
        dataset=norm_ds,
        completion_id=0,
        problem=problem,
        solution=solution_code,
        expected_output=expected_output,
        base_only=base_only,
        fast_check=fast_check,
    )

    base_stat, base_details = res["base"]
    plus_stat = None
    plus_details = []

    if not base_only and "plus" in res:
        plus_stat, plus_details = res["plus"]

    # Ground truth determination:
    # A program is clean (is_hallucinated=False) iff base_status == 'pass' AND (base_only or plus_status == 'pass').
    # Any failure on base or plus indicates an actual functional or edge-case hallucination.
    base_passed = (base_stat == "pass")
    plus_passed = (plus_stat == "pass") if not base_only else True
    is_hallucinated = not (base_passed and plus_passed)

    return {
        "base_status": base_stat,
        "plus_status": plus_stat,
        "base_details": [bool(b) for b in base_details],
        "plus_details": [bool(p) for p in plus_details] if plus_details is not None else [],
        "is_hallucinated": is_hallucinated,
    }


# =====================================================================
# 5. Conversion to Canonical DatasetRecord
# =====================================================================

def convert_to_dataset_record(
    problem: Dict[str, Any],
    raw_code: str,
    sanitized_code: str,
    eval_result: Dict[str, Any],
    dataset: str,
    model_name: str,
    oracle: Dict[str, Any]
) -> Any:
    """
    Converts an evaluated EvalPlus sample into the project's canonical DatasetRecord schema.
    """
    from dataset_loaders import DatasetRecord

    task_id = problem["task_id"]
    norm_ds = "MBPP" if "mbpp" in dataset.lower() else "HumanEval"
    unified_ds_name = f"EvalPlus-{norm_ds}"
    entry_point = problem.get("entry_point", "")

    # Build tests list
    formatted_tests: List[Dict[str, Any]] = []

    # 1. Human-readable assertion strings if available
    if "assertion" in problem and problem["assertion"]:
        for line in problem["assertion"].strip().split("\n"):
            line = line.strip()
            if line:
                formatted_tests.append({"assertion": line, "type": "base_assert"})
    elif "test" in problem and problem["test"]:
        formatted_tests.append({"assertion": problem["test"], "type": "check_func"})

    # 2. Base test inputs & expected oracle outputs
    base_inputs = problem.get("base_input", [])
    base_expected = oracle.get("base", [])
    for inp, exp in zip(base_inputs[:10], base_expected[:10]):  # Keep first 10 for compact representation
        formatted_tests.append({
            "input": inp,
            "expected_output": exp,
            "type": "base_input"
        })

    # Ground truth labels
    is_hallu = eval_result["is_hallucinated"]
    labels: List[Dict[str, Any]] = []
    if is_hallu:
        base_stat = eval_result.get("base_status")
        if base_stat != "pass":
            labels.append({
                "type_code": "LFH",
                "error_type": "Logical Failure Hallucination (fails prompt base tests)"
            })
        else:
            labels.append({
                "type_code": "LDH",
                "error_type": "Logical Deviation Hallucination (passes base tests, fails plus tests)"
            })

    # Metadata
    metadata = {
        "model": model_name,
        "raw_code": raw_code,
        "entry_point": entry_point,
        "base_status": eval_result.get("base_status"),
        "plus_status": eval_result.get("plus_status"),
        "base_tests_passed": sum(eval_result.get("base_details", [])),
        "base_tests_total": len(eval_result.get("base_details", [])),
        "plus_tests_passed": sum(eval_result.get("plus_details", [])),
        "plus_tests_total": len(eval_result.get("plus_details", [])),
        "source": "evalplus_github_release",
    }

    return DatasetRecord(
        task_id=f"EvalPlus/{task_id}",
        dataset=unified_ds_name,
        prompt=problem.get("prompt", ""),
        code=sanitized_code,
        clean_code=problem.get("canonical_solution"),
        tests=formatted_tests,
        ground_truth_labels=labels,
        is_hallucinated=is_hallu,
        metadata=metadata
    )


# =====================================================================
# 6. High-Level Pipeline: Fetch, Evaluate, and Build Records
# =====================================================================

def fetch_and_evaluate_evalplus(
    dataset: str = "humaneval",
    model: str = "chatgpt",
    limit: Optional[int] = None,
    save_path: Optional[str] = None,
    base_only: bool = False,
    fast_check: bool = True,
    cache_dir: Optional[str] = None,
    verbose: bool = True
) -> List[Any]:
    """
    End-to-end pipeline:
    1. Downloads pre-generated completions from EvalPlus GitHub releases.
    2. Loads problem definitions and ground-truth oracle outputs.
    3. Executes solutions in EvalPlus's sandbox to obtain empirical pass/fail labels.
    4. Converts samples into canonical DatasetRecord format.
    5. Optionally saves evaluated records as JSON.

    Returns:
        List of DatasetRecord instances.
    """
    apply_windows_patches()
    import evalplus.sanitize as es
    from evalplus.data import (
        get_human_eval_plus,
        get_human_eval_plus_hash,
        get_mbpp_plus,
        get_mbpp_plus_hash,
        load_solutions,
    )
    from evalplus.evaluate import get_groundtruth, MBPP_OUTPUT_NOT_NONE_TASKS

    norm_ds = "mbpp" if "mbpp" in dataset.lower() else "humaneval"

    if verbose:
        print(f"[EvalPlusFetcher] Step 1: Downloading/extracting '{norm_ds}' samples for model '{model}'...")
    samples_dir = fetch_evalplus_samples(dataset=norm_ds, model=model, cache_dir=cache_dir)
    if verbose:
        print(f"[EvalPlusFetcher] Samples directory: {samples_dir}")

    # Load problem suite
    if verbose:
        print(f"[EvalPlusFetcher] Step 2: Loading {norm_ds.upper()}+ dataset problems...")
    
    import pickle
    from evalplus.evaluate import CACHE_DIR, MBPP_OUTPUT_NOT_NONE_TASKS

    cached_gt = None
    if norm_ds == "humaneval":
        problems = get_human_eval_plus()
        hashcode = get_human_eval_plus_hash()
    else:
        problems = get_mbpp_plus()
        hashcode = get_mbpp_plus_hash()

    cache_file = os.path.join(CACHE_DIR, f"{hashcode}.pkl")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "rb") as f:
                cached_gt = pickle.load(f)
            if verbose:
                print(f"[EvalPlusFetcher] Loaded ground-truth oracle from cache ({cache_file}).")
        except Exception as e:
            if verbose:
                print(f"[EvalPlusFetcher] Cache load failed ({e}); will compute ground truth per task.")
            cached_gt = None
    else:
        if verbose:
            print("[EvalPlusFetcher] Pre-existing global cache not found; computing ground truth on the fly per evaluated task.")

    # Iterate over solutions
    records: List[Any] = []
    processed_count = 0
    clean_count = 0
    hallu_count = 0

    if verbose:
        print(f"[EvalPlusFetcher] Step 3: Evaluating samples with EvalPlus oracle ground truth...")

    for item in load_solutions(samples_dir):
        task_id = item["task_id"]
        if task_id not in problems:
            continue

        prob = problems[task_id]
        raw_code = item.get("solution", "")
        if not raw_code and "completion" in item:
            raw_code = prob["prompt"] + item["completion"]

        # Clean/sanitize code
        entry_point = prob.get("entry_point")
        sanitized_code = es.sanitize(raw_code, entry_point)

        # Get or compute ground truth for this task
        oracle = get_or_compute_task_groundtruth(prob, norm_ds, cached_gt)

        # Run EvalPlus evaluator
        eval_res = evaluate_single_sample(
            problem=prob,
            solution_code=sanitized_code,
            dataset=norm_ds,
            expected_output=oracle,
            base_only=base_only,
            fast_check=fast_check
        )

        record = convert_to_dataset_record(
            problem=prob,
            raw_code=raw_code,
            sanitized_code=sanitized_code,
            eval_result=eval_res,
            dataset=norm_ds,
            model_name=model,
            oracle=oracle
        )
        records.append(record)

        if record.is_hallucinated:
            hallu_count += 1
        else:
            clean_count += 1

        processed_count += 1
        if verbose and (processed_count % 25 == 0 or processed_count == limit):
            print(f"[EvalPlusFetcher] Progress: {processed_count} evaluated "
                  f"(Clean: {clean_count}, Hallucinated: {hallu_count})")

        if limit is not None and processed_count >= limit:
            break

    if verbose:
        print(f"[EvalPlusFetcher] Done! Total evaluated: {len(records)} "
              f"(Clean: {clean_count}, Hallucinated: {hallu_count})")

    # Save to JSON if requested
    if save_path:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        save_dataset_records(records, save_path)
        if verbose:
            print(f"[EvalPlusFetcher] Saved {len(records)} records to {save_path}")

    return records


# =====================================================================
# 7. Serialization Helpers
# =====================================================================

def save_dataset_records(records: List[Any], filepath: str) -> None:
    """Serializes a list of DatasetRecord instances to a JSON file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    serialized = [r.to_dict() if hasattr(r, "to_dict") else r for r in records]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2)


def load_dataset_records_from_file(filepath: str) -> List[Any]:
    """Deserializes a JSON file into DatasetRecord instances."""
    from dataset_loaders import DatasetRecord
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Records file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    records: List[DatasetRecord] = []
    for item in raw_list:
        records.append(DatasetRecord(
            task_id=item["task_id"],
            dataset=item["dataset"],
            prompt=item["prompt"],
            code=item["code"],
            clean_code=item.get("clean_code"),
            tests=item.get("tests", []),
            ground_truth_labels=item.get("ground_truth_labels", []),
            is_hallucinated=item.get("is_hallucinated", False),
            metadata=item.get("metadata", {})
        ))
    return records


# =====================================================================
# 8. Command-Line Interface
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fetch EvalPlus pre-generated LLM completions, run oracle evaluation, and export DatasetRecords."
    )
    parser.add_argument(
        "--dataset",
        choices=["humaneval", "mbpp"],
        default="humaneval",
        help="Target benchmark dataset (humaneval or mbpp)."
    )
    parser.add_argument(
        "--model",
        default="chatgpt",
        help="Pre-generated model alias (e.g. chatgpt, starcoder, gpt-3.5-turbo, gpt-4)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of tasks to evaluate."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path for saving DatasetRecords JSON."
    )
    parser.add_argument(
        "--base-only",
        action="store_true",
        help="Evaluate on base tests only (skip plus tests)."
    )
    args = parser.parse_args()

    default_out = args.output or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data",
        "evalplus",
        f"{args.dataset}_{args.model}_records.json"
    )

    records = fetch_and_evaluate_evalplus(
        dataset=args.dataset,
        model=args.model,
        limit=args.limit,
        save_path=default_out,
        base_only=args.base_only,
        verbose=True
    )
    print(f"\nCompleted successfully! {len(records)} records exported to {default_out}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
