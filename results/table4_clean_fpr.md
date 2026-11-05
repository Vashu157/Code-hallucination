# Empirical Clean-Code Specificity Diagnostic (MBPP Clean Tasks)

Evaluates detector specificity and false alarm rates on verified human-written clean code.
Reports 95% Wilson confidence intervals to prevent overinterpreting small-sample variations.

| Method | Clean Tasks | False Positives (FP) | True Negatives (TN) | FPR (%) | FPR 95% CI | Specificity (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **SDHD** | 10 | 1 | 9 | 10.0% | [1.8%, 40.4%] | 90.0% |
| CodeHalu | 10 | 0 | 10 | 0.0% | [0.0%, 27.8%] | 100.0% |
| SelfCheck | 10 | 0 | 10 | 0.0% | [0.0%, 27.8%] | 100.0% |
| SAC3 | 10 | 8 | 2 | 80.0% | [49.0%, 94.3%] | 20.0% |

> [!NOTE]
> In the IEEE TSE 2026 paper, Table IV is strictly 'A Comparison Between Static and Dynamic Methods'
> across MBPP, CHE, and HC (reported in the ablation study). The paper does not print an FPR table.
> This diagnostic measures how well static invariants and dynamic execution avoid false alarms on verified clean code.