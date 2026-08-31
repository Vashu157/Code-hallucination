# Table III: Hallucination Detection Performance (RQ1 Reproduction)

| Dataset | Method | Precision | Recall | F1 Score | Accuracy | FPR |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **MBPP** | **SDHD** | 0.000 | 0.000 | **0.000** | 0.900 | 0.100 |
| **MBPP** | **CodeHalu** | 0.000 | 0.000 | **0.000** | 1.000 | 0.000 |
| **MBPP** | **SelfCheck** | 0.000 | 0.000 | **0.000** | 1.000 | 0.000 |
| **MBPP** | **SAC3** | 0.000 | 0.000 | **0.000** | 0.000 | 1.000 |
| **CodeHaluEval** | **SDHD** | 1.000 | 1.000 | **1.000** | 1.000 | 0.000 |
| **CodeHaluEval** | **CodeHalu** | 1.000 | 1.000 | **1.000** | 1.000 | 0.000 |
| **CodeHaluEval** | **SelfCheck** | 0.000 | 0.000 | **0.000** | 0.200 | 0.000 |
| **CodeHaluEval** | **SAC3** | 0.800 | 1.000 | **0.889** | 0.800 | 1.000 |
| **HalluCode** | **SDHD** | 0.857 | 1.000 | **0.923** | 0.857 | 1.000 |
| **HalluCode** | **CodeHalu** | 0.000 | 0.000 | **0.000** | 0.143 | 0.000 |
| **HalluCode** | **SelfCheck** | 0.000 | 0.000 | **0.000** | 0.143 | 0.000 |
| **HalluCode** | **SAC3** | 0.857 | 1.000 | **0.923** | 0.857 | 1.000 |
| **Combined** | **SDHD** | 0.833 | 1.000 | **0.909** | 0.909 | 0.167 |
| **Combined** | **CodeHalu** | 1.000 | 0.400 | **0.571** | 0.727 | 0.000 |
| **Combined** | **SelfCheck** | 0.000 | 0.000 | **0.000** | 0.545 | 0.000 |
| **Combined** | **SAC3** | 0.455 | 1.000 | **0.625** | 0.455 | 1.000 |

### Statistical Significance (McNemar Test on Combined Split)
| Comparison | SDHD Wins | Baseline Wins | Chi² Stat | p-value | Significant (p < 0.05) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| SDHD_vs_CodeHalu | 6 | 2 | 1.125 | 0.288844 | No |
| SDHD_vs_SelfCheck | 10 | 2 | 4.0833 | 0.043308 | Yes (p < 0.05) |
| SDHD_vs_SAC3 | 10 | 0 | 8.1 | 0.004427 | Yes (p < 0.05) |