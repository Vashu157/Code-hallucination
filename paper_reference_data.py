"""
paper_reference_data.py - Ground Truth Published Values from Yang et al. (IEEE TSE 2026)
========================================================================================
Paper: "Advancing LLM-Generated Code Reliability: A Hybrid Approach for Hallucination Detection"
Authors: Bo Yang, Jiayi Dang, Huai Liu, Zhi Jin
IEEE Transactions on Software Engineering, Vol. 52, No. 2, February 2026, pp. 581-594.

This module provides the EXACT values printed in the base paper for:
- Table II: Dataset Statistics
- Table III: RQ1 Hallucination Detection Result (P, R, F1 on MBPP, CHE, HC)
- Table IV: RQ2 Static vs. Dynamic Ablation (P, R, F1 on MBPP, CHE, HC)
- Table V: RQ3 Test Suite Size Sensitivity (P, R, F1 on MBPP, CHE, HC)
- Table VI: RQ4 Program Representation (AST, AST+CFG, SSA on MBPP, CHE, HC)
- Table VII: RQ5 8-Type Category Breakdown Matrix for SDHD (P, R, F1 on MBPP, CHE, HC)

IMPORTANT NOTES ON PAPER REPORTING:
1. The paper reports ONLY Precision (P), Recall (R), and F1-score (F1).
   It does NOT report Accuracy, FPR, or Specificity in any table.
2. The paper evaluates on three datasets:
   - MBPP (974 tasks)
   - CHE (CodeHaluEval, 699 tasks)
   - HC (HalluCode, 5664 tasks)
   It does NOT report a "Combined" column in its tables.
3. Table IV is strictly the component ablation (Static-only vs Dynamic-only vs SDHD).
   There is NO "Table IV Clean FPR on MBPP" in the paper.
"""

from typing import Dict, Any

# Table II: Detailed Statistics on Datasets (Page 9)
TABLE_II_DATASETS: Dict[str, Dict[str, Any]] = {
    "MBPP": {
        "year": 2021,
        "language": "Python",
        "construction": "Manual",
        "tasks": 974,
        "avg_tests_per_task": 3.0,
        "avg_tokens_per_sample": 24.2,
    },
    "CodeHaluEval": {
        "year": 2024,
        "language": "Python",
        "construction": "Automated",
        "tasks": 699,
        "avg_tests_per_task": 12.8,
        "avg_tokens_per_sample": 293.2,
    },
    "HalluCode": {
        "year": 2024,
        "language": "Python",
        "construction": "Automated+Manual",
        "tasks": 5664,
        "avg_tests_per_task": None,  # Marked as N/A in Table II
        "avg_tokens_per_sample": 54.1,
    },
}

# Table III: Hallucination Detection Result (Page 10)
# Models evaluated: CodeHalu, Selfcheck, SCA3, SDHD
# Columns: MBPP, CHE, HC
# Metrics: P, R, F1
TABLE_III_RQ1: Dict[str, Dict[str, Dict[str, float]]] = {
    "CodeHalu": {
        "MBPP": {"P": 0.445, "R": 0.557, "F1": 0.496},
        "CHE":  {"P": 0.457, "R": 0.530, "F1": 0.492},
        "HC":   {"P": 0.452, "R": 0.514, "F1": 0.482},
    },
    "Selfcheck": {
        "MBPP": {"P": 0.160, "R": 0.270, "F1": 0.201},
        "CHE":  {"P": 0.122, "R": 0.223, "F1": 0.157},
        "HC":   {"P": 0.140, "R": 0.250, "F1": 0.176},
    },
    "SCA3": {
        "MBPP": {"P": 0.278, "R": 0.389, "F1": 0.324},
        "CHE":  {"P": 0.240, "R": 0.360, "F1": 0.288},
        "HC":   {"P": 0.300, "R": 0.333, "F1": 0.316},
    },
    "SDHD": {
        "MBPP": {"P": 0.775, "R": 0.778, "F1": 0.776},
        "CHE":  {"P": 0.770, "R": 0.780, "F1": 0.773},
        "HC":   {"P": 0.768, "R": 0.790, "F1": 0.778},
    },
}

# Table IV: A Comparison Between Static and Dynamic Methods (Page 11)
# Models: Static-only, Dynamic-only, SDHD
# Columns: MBPP, CHE, HC
# Metrics: P, R, F1
TABLE_IV_RQ2: Dict[str, Dict[str, Dict[str, float]]] = {
    "Static-only": {
        "MBPP": {"P": 0.473, "R": 0.487, "F1": 0.480},
        "CHE":  {"P": 0.467, "R": 0.453, "F1": 0.465},
        "HC":   {"P": 0.500, "R": 0.444, "F1": 0.471},
    },
    "Dynamic-only": {
        "MBPP": {"P": 0.750, "R": 0.700, "F1": 0.724},
        "CHE":  {"P": 0.720, "R": 0.700, "F1": 0.693},
        "HC":   {"P": 0.731, "R": 0.739, "F1": 0.735},
    },
    "SDHD": {
        "MBPP": {"P": 0.775, "R": 0.778, "F1": 0.776},
        "CHE":  {"P": 0.770, "R": 0.780, "F1": 0.773},
        "HC":   {"P": 0.768, "R": 0.790, "F1": 0.778},
    },
}

# Table V: An Ablation Study About the Number of Test Cases (Page 12)
# Buckets: N < 3, 3 <= N < 10, 10 <= N <= 15
# Columns: MBPP, CHE, HC
# Metrics: P, R, F1
TABLE_V_RQ3: Dict[str, Dict[str, Dict[str, float]]] = {
    "N < 3": {
        "MBPP": {"P": 0.443, "R": 0.542, "F1": 0.487},
        "CHE":  {"P": 0.452, "R": 0.514, "F1": 0.485},
        "HC":   {"P": 0.490, "R": 0.479, "F1": 0.482},
    },
    "3 <= N < 10": {
        "MBPP": {"P": 0.466, "R": 0.496, "F1": 0.511},
        "CHE":  {"P": 0.491, "R": 0.494, "F1": 0.492},
        "HC":   {"P": 0.521, "R": 0.523, "F1": 0.522},
    },
    "10 <= N <= 15": {
        "MBPP": {"P": 0.748, "R": 0.702, "F1": 0.724},
        "CHE":  {"P": 0.725, "R": 0.706, "F1": 0.715},
        "HC":   {"P": 0.733, "R": 0.727, "F1": 0.730},
    },
}

# Table VI: Comparative Experimental Results Among AST, AST+CFG and Static Detection (Page 12)
# Models: AST, AST+CFG, SSA
# Columns: MBPP, CHE, HC
# Metrics: P, R, F1
TABLE_VI_RQ4: Dict[str, Dict[str, Dict[str, float]]] = {
    "AST": {
        "MBPP": {"P": 0.290, "R": 0.320, "F1": 0.304},
        "CHE":  {"P": 0.270, "R": 0.340, "F1": 0.303},
        "HC":   {"P": 0.320, "R": 0.330, "F1": 0.325},
    },
    "AST+CFG": {
        "MBPP": {"P": 0.314, "R": 0.309, "F1": 0.311},
        "CHE":  {"P": 0.306, "R": 0.363, "F1": 0.332},
        "HC":   {"P": 0.334, "R": 0.353, "F1": 0.343},
    },
    "SSA": {
        "MBPP": {"P": 0.473, "R": 0.487, "F1": 0.480},
        "CHE":  {"P": 0.467, "R": 0.453, "F1": 0.465},
        "HC":   {"P": 0.500, "R": 0.444, "F1": 0.471},
    },
}

# Table VII: Experimental Results on Different Types of Hallucinations (Page 13)
# Reports SDHD performance across 8 categories:
# MH: DCH, SAH
# NH: IH, ESH
# RH: PCH, CBH
# LH: LDH, LFH
# Rows: MBPP, CHE, HC
TABLE_VII_RQ5: Dict[str, Dict[str, Dict[str, float]]] = {
    "MBPP": {
        "DCH": {"P": 0.744, "R": 0.860, "F1": 0.798},
        "SAH": {"P": 0.467, "R": 0.491, "F1": 0.479},
        "IH":  {"P": 0.403, "R": 0.428, "F1": 0.416},
        "ESH": {"P": 0.793, "R": 0.751, "F1": 0.771},
        "PCH": {"P": 0.511, "R": 0.753, "F1": 0.608},
        "CBH": {"P": 0.440, "R": 0.403, "F1": 0.421},
        "LDH": {"P": 0.815, "R": 0.826, "F1": 0.820},
        "LFH": {"P": 0.363, "R": 0.369, "F1": 0.366},
    },
    "CHE": {
        "DCH": {"P": 0.732, "R": 0.844, "F1": 0.781},
        "SAH": {"P": 0.481, "R": 0.455, "F1": 0.467},
        "IH":  {"P": 0.440, "R": 0.460, "F1": 0.450},
        "ESH": {"P": 0.800, "R": 0.691, "F1": 0.743},
        "PCH": {"P": 0.501, "R": 0.740, "F1": 0.597},
        "CBH": {"P": 0.451, "R": 0.433, "F1": 0.442},
        "LDH": {"P": 0.801, "R": 0.833, "F1": 0.817},
        "LFH": {"P": 0.410, "R": 0.409, "F1": 0.409},
    },
    "HC": {
        "DCH": {"P": 0.736, "R": 0.722, "F1": 0.729},
        "SAH": {"P": 0.438, "R": 0.466, "F1": 0.450},
        "IH":  {"P": 0.411, "R": 0.405, "F1": 0.406},
        "ESH": {"P": 0.780, "R": 0.693, "F1": 0.734},
        "PCH": {"P": 0.514, "R": 0.503, "F1": 0.508},
        "CBH": {"P": 0.439, "R": 0.404, "F1": 0.421},
        "LDH": {"P": 0.806, "R": 0.811, "F1": 0.809},
        "LFH": {"P": 0.397, "R": 0.361, "F1": 0.379},
    },
}
