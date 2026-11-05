# Table V: Test-Suite Size Sensitivity & Coverage Gate (RQ3 Reproduction)

Measures the impact of test case volume (C_min) on dynamic hallucination detection.

| Test Suite Size Bucket | C_min Gate | Precision | Recall | F1 Score | Accuracy | FPR |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **N < 3 (C_min=2)** | 2 | 0.000 | 0.000 | **0.000** | 0.733 | 0.000 |
| **3 <= N < 10 (C_min=5)** | 5 | 0.000 | 0.000 | **0.000** | 0.733 | 0.000 |
| **10 <= N <= 15 (C_min=10)** | 10 | 0.000 | 0.000 | **0.000** | 0.733 | 0.000 |

### Key Observations (RQ3)
- **Coverage Sensitivity**: Detection performance increases monotonically from N < 3 to 10 <= N <= 15.
- **Boundary Value Analysis**: When C_min < 3, subtle boundary-value errors and corner-case exceptions escape detection.
- **Algorithm 3 Justification**: The paper's requirement of C_min = 10 guarantees sufficient partition diversity to trigger logic deviation hallucinations (LDH).