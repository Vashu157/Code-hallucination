# Table IV: Clean-Code False Positive Rate (MBPP Clean Pool)

Evaluates detector specificity and false alarm rates on verified non-hallucinated tasks.

| Method | Clean Tasks | False Positives (FP) | True Negatives (TN) | FPR (%) | Specificity (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **SDHD** | 10 | 1 | 9 | 10.0% | 90.0% |
| CodeHalu | 10 | 0 | 10 | 0.0% | 100.0% |
| SelfCheck | 10 | 0 | 10 | 0.0% | 100.0% |
| SAC3 | 10 | 10 | 0 | 100.0% | 0.0% |

> [!NOTE]
> Lower FPR is strictly better. SDHD suppresses false alarms by requiring confirmed
> SSA variable lifecycle violations or test execution failures before flagging.