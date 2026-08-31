# Table IV: Ablation Study of SDHD Components (RQ2 Reproduction)

| Dataset | Method | Precision | Recall | F1 Score | Accuracy | FPR |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **MBPP** | SDHD-S | 0.000 | 0.000 | **0.000** | 0.900 | 0.100 |
| **MBPP** | SDHD-D | 0.000 | 0.000 | **0.000** | 1.000 | 0.000 |
| **MBPP** | **SDHD** | 0.000 | 0.000 | **0.000** | 0.900 | 0.100 |
| **CodeHaluEval** | SDHD-S | 0.000 | 0.000 | **0.000** | 0.200 | 0.000 |
| **CodeHaluEval** | SDHD-D | 1.000 | 1.000 | **1.000** | 1.000 | 0.000 |
| **CodeHaluEval** | **SDHD** | 1.000 | 1.000 | **1.000** | 1.000 | 0.000 |
| **HalluCode** | SDHD-S | 0.857 | 1.000 | **0.923** | 0.857 | 1.000 |
| **HalluCode** | SDHD-D | 0.857 | 1.000 | **0.923** | 0.857 | 1.000 |
| **HalluCode** | **SDHD** | 0.857 | 1.000 | **0.923** | 0.857 | 1.000 |
| **Combined** | SDHD-S | 0.750 | 0.600 | **0.667** | 0.727 | 0.167 |
| **Combined** | SDHD-D | 0.909 | 1.000 | **0.952** | 0.955 | 0.083 |
| **Combined** | **SDHD** | 0.833 | 1.000 | **0.909** | 0.909 | 0.167 |