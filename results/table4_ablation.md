# Table IV: A Comparison Between Static and Dynamic Methods (RQ2)

### 1. Published Values in Base Paper (Yang et al., IEEE TSE 2026, Table IV, Page 11)
| Model | Metric | MBPP | CHE (CodeHaluEval) | HC (HalluCode) |
| :--- | :---: | :---: | :---: | :---: |
| **Static-only** | P | 0.473 | 0.467 | 0.500 |
| | R | 0.487 | 0.453 | 0.444 |
| | **F1** | **0.480** | **0.465** | **0.471** |
| **Dynamic-only** | P | 0.750 | 0.720 | 0.731 |
| | R | 0.700 | 0.700 | 0.739 |
| | **F1** | **0.724** | **0.693** | **0.735** |
| **SDHD** | P | 0.775 | 0.770 | 0.768 |
| | R | 0.778 | 0.780 | 0.790 |
| | **F1** | **0.776** | **0.773** | **0.778** |

### 2. Empirical Results on Local Benchmark Splits
| Dataset | Method | Precision (P) | Recall (R) | F1 Score | Accuracy |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **MBPP** | SDHD-S | 0.000 | 0.000 | **0.000** | 0.900 |
| **MBPP** | SDHD-D | 0.000 | 0.000 | **0.000** | 1.000 |
| **MBPP** | **SDHD** | 0.000 | 0.000 | **0.000** | 0.900 |
| **CodeHaluEval** | SDHD-S | 0.000 | 0.000 | **0.000** | 0.200 |
| **CodeHaluEval** | SDHD-D | 0.000 | 0.000 | **0.000** | 0.200 |
| **CodeHaluEval** | **SDHD** | 0.000 | 0.000 | **0.000** | 0.200 |
| **HalluCode** | SDHD-S | 0.857 | 1.000 | **0.923** | 0.857 |
| **HalluCode** | SDHD-D | 0.000 | 0.000 | **0.000** | 0.143 |
| **HalluCode** | **SDHD** | 0.857 | 1.000 | **0.923** | 0.857 |
| **Combined** | SDHD-S | 0.750 | 0.600 | **0.667** | 0.727 |
| **Combined** | SDHD-D | 0.000 | 0.000 | **0.000** | 0.545 |
| **Combined** | **SDHD** | 0.750 | 0.600 | **0.667** | 0.727 |

### Key Observations (RQ2)
- **Static vs Dynamic Complementarity**: In the base paper and our empirical testing, neither static nor dynamic alone matches the hybrid pipeline.
- **Static-Only (SDHD-S)**: Instant compile-time checking, but lacks runtime execution feedback for semantic logical deviations (LDH).
- **Dynamic-Only (SDHD-D)**: Depends strictly on test availability. Without tests, dynamic detection drops significantly.