# Table III: Hallucination Detection Result (Paper vs. Empirical Reproduction)

### 1. Published Values in Base Paper (Yang et al., IEEE TSE 2026, Table III, Page 10)
| Model | Metric | MBPP | CHE (CodeHaluEval) | HC (HalluCode) |
| :--- | :---: | :---: | :---: | :---: |
| **CodeHalu** | P | 0.445 | 0.457 | 0.452 |
| | R | 0.557 | 0.530 | 0.514 |
| | **F1** | **0.496** | **0.492** | **0.482** |
| **Selfcheck** | P | 0.160 | 0.122 | 0.140 |
| | R | 0.270 | 0.223 | 0.250 |
| | **F1** | **0.201** | **0.157** | **0.176** |
| **SCA3** | P | 0.278 | 0.240 | 0.300 |
| | R | 0.389 | 0.360 | 0.333 |
| | **F1** | **0.324** | **0.288** | **0.316** |
| **SDHD** | P | 0.775 | 0.770 | 0.768 |
| | R | 0.778 | 0.780 | 0.790 |
| | **F1** | **0.776** | **0.773** | **0.778** |

*(Note: HalluCode (HC) dataset is an unreleased private author artifact; see Section V-F threats to validity.)*

### 2. Empirical Results on Local Benchmark Splits
| Dataset | Method | Precision (P) | Recall (R) | F1 Score | Accuracy |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **MBPP** | **SDHD** | 0.000 | 0.000 | **0.000** | 0.900 |
| **MBPP** | CodeHalu | 0.000 | 0.000 | **0.000** | 1.000 |
| **MBPP** | SelfCheck | 0.000 | 0.000 | **0.000** | 1.000 |
| **MBPP** | SAC3 | 0.000 | 0.000 | **0.000** | 0.200 |
| **CodeHaluEval** | **SDHD** | 0.000 | 0.000 | **0.000** | 0.200 |
| **CodeHaluEval** | CodeHalu | 0.000 | 0.000 | **0.000** | 0.200 |
| **CodeHaluEval** | SelfCheck | 0.000 | 0.000 | **0.000** | 0.200 |
| **CodeHaluEval** | SAC3 | 0.500 | 0.250 | **0.333** | 0.200 |
| **HalluCode** | **SDHD** | 0.857 | 1.000 | **0.923** | 0.857 |
| **HalluCode** | CodeHalu | 0.000 | 0.000 | **0.000** | 0.143 |
| **HalluCode** | SelfCheck | 1.000 | 0.333 | **0.500** | 0.429 |
| **HalluCode** | SAC3 | 1.000 | 0.333 | **0.500** | 0.429 |
| **Combined** | **SDHD** | 0.750 | 0.600 | **0.667** | 0.727 |
| **Combined** | CodeHalu | 0.000 | 0.000 | **0.000** | 0.545 |
| **Combined** | SelfCheck | 1.000 | 0.200 | **0.333** | 0.636 |
| **Combined** | SAC3 | 0.250 | 0.300 | **0.273** | 0.273 |

### Statistical Significance (McNemar Test on Combined Split)
| Comparison | SDHD Wins | Baseline Wins | Chi2 Stat | p-value | Significant (p < 0.05) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| SDHD_vs_CodeHalu | 6 | 2 | 1.125 | 0.288844 | No |
| SDHD_vs_SelfCheck | 4 | 2 | 0.1667 | 0.683091 | No |
| SDHD_vs_SAC3 | 12 | 2 | 5.7857 | 0.016157 | Yes (p < 0.05) |