"""
download_datasets.py - Automated Downloader for Empirical Benchmark Datasets
=============================================================================
Downloads:
1. MBPP (Mostly Basic Python Problems):
   Source: Google Research GitHub (Austin et al., 2021)
   File: https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl
   Tasks: 974 programming tasks with tests.

2. CodeHaluEval:
   Source: Hugging Face (Yuchen111/CodeHaluEval) (Tian et al., 2024)
   Files: All 8 canonical hallucination categories:
     - data_compliance_hallucination.json (DCH)
     - structural_access_hallucination.json (SAH)
     - identification_hallucination.json (IH)
     - external_source_hallucination.json (ESH)
     - physical_constraint_hallucination.json (PCH)
     - calculate_boundary_hallucination.json (CBH)
     - logic_deviation.json (LDH)
     - logic_breakdown.json (LFH/LBH)
"""

import os
import sys
import time
import urllib.request
import json
from typing import List, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CODEHALU_DIR = os.path.join(DATA_DIR, "codehalueval")


def download_file(url: str, dest_path: str, chunk_size: int = 1024 * 64) -> bool:
    """Downloads a file with streaming chunks and progress display."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    temp_path = dest_path + ".tmp"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp, open(temp_path, "wb") as out_file:
            total_size = resp.headers.get("content-length")
            total_bytes = int(total_size) if total_size else None
            downloaded = 0
            start_time = time.time()

            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)

                if total_bytes:
                    pct = (downloaded / total_bytes) * 100
                    mb = downloaded / (1024 * 1024)
                    tot_mb = total_bytes / (1024 * 1024)
                    sys.stdout.write(f"\r  [{pct:5.1f}%] {mb:.2f} / {tot_mb:.2f} MB")
                else:
                    mb = downloaded / (1024 * 1024)
                    sys.stdout.write(f"\r  Downloaded: {mb:.2f} MB")
                sys.stdout.flush()

        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(temp_path, dest_path)
        elapsed = time.time() - start_time
        print(f" -> Completed in {elapsed:.1f}s ({os.path.getsize(dest_path)/(1024*1024):.2f} MB)")
        return True

    except Exception as e:
        print(f"\n  [ERROR] Failed to download {url}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return False


def download_mbpp() -> bool:
    """Downloads the complete MBPP dataset from Google Research."""
    url = "https://raw.githubusercontent.com/google-research/google-research/master/mbpp/mbpp.jsonl"
    dest = os.path.join(DATA_DIR, "mbpp.jsonl")
    print(f"\n[1/2] Downloading MBPP (974 tasks) from Google Research...")
    print(f"  URL: {url}")
    print(f"  Dest: {dest}")
    if os.path.exists(dest) and os.path.getsize(dest) > 100000:
        print(f"  [Cache hit] MBPP already exists ({os.path.getsize(dest)/(1024*1024):.2f} MB). Skipping download.")
        return True
    return download_file(url, dest)


def download_codehalueval(categories: Optional[List[str]] = None) -> List[str]:
    """Downloads CodeHaluEval datasets from Hugging Face across all 8 canonical categories."""
    base_url = "https://huggingface.co/datasets/Yuchen111/CodeHaluEval/resolve/main/"
    all_files = [
        "data_compliance_hallucination.json",
        "structural_access_hallucination.json",
        "identification_hallucination.json",
        "external_source_hallucination.json",
        "physical_constraint_hallucination.json",
        "calculate_boundary_hallucination.json",
        "logic_deviation.json",
        "logic_breakdown.json"
    ]

    targets = categories if categories else all_files
    print(f"\n[2/2] Downloading CodeHaluEval ({len(targets)} categories) from Hugging Face...")

    downloaded = []
    for i, fname in enumerate(targets, 1):
        url = base_url + fname
        dest = os.path.join(CODEHALU_DIR, fname)
        print(f"\n({i}/{len(targets)}) Downloading {fname}...")
        if os.path.exists(dest) and os.path.getsize(dest) > 100000:
            print(f"  [Cache hit] {fname} already exists ({os.path.getsize(dest)/(1024*1024):.2f} MB). Skipping.")
            downloaded.append(dest)
            continue
        ok = download_file(url, dest)
        if ok:
            downloaded.append(dest)

    return downloaded


def verify_downloaded_datasets():
    """Validates the downloaded files, reporting record counts and schema inspection."""
    print("\n" + "="*70)
    print("VERIFICATION OF DOWNLOADED BENCHMARK DATASETS")
    print("="*70)

    # 1. MBPP Verification
    mbpp_path = os.path.join(DATA_DIR, "mbpp.jsonl")
    if os.path.exists(mbpp_path):
        task_count = 0
        with open(mbpp_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    task_count += 1
        print(f"MBPP (Google Research):")
        print(f"  File: {mbpp_path}")
        print(f"  Total Tasks: {task_count} (Matches paper Table II: 974 tasks: {task_count == 974})")
    else:
        print(f"MBPP: Not found at {mbpp_path}")

    # 2. CodeHaluEval Verification
    print(f"\nCodeHaluEval (Hugging Face Yuchen111/CodeHaluEval):")
    if os.path.exists(CODEHALU_DIR):
        total_che_samples = 0
        for fname in sorted(os.listdir(CODEHALU_DIR)):
            if fname.endswith(".json"):
                fpath = os.path.join(CODEHALU_DIR, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                    cnt = len(data) if isinstance(data, list) else 0
                    total_che_samples += cnt
                    print(f"  - {fname:42s}: {cnt:5d} records ({os.path.getsize(fpath)/(1024*1024):5.1f} MB)")
                except Exception as e:
                    print(f"  - {fname}: Error reading ({e})")
        print(f"  Total CodeHaluEval Samples Across Categories: {total_che_samples}")
    else:
        print("  CodeHaluEval directory not found.")
    print("="*70)


if __name__ == "__main__":
    download_mbpp()
    # Download all 8 categories
    download_codehalueval()
    verify_downloaded_datasets()
