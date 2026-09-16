# Table VII: Hallucination Category Breakdown Matrix (RQ1 Reproduction)

Measures detection count and recall rate across the 8 canonical hallucination categories.

| Code | Hallucination Category | Ground Truth | SDHD | CodeHalu | SelfCheck | SAC3 |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **DCH** | Data Compliance Hallucination (DCH) | 1 | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **SAH** | Structure Access Hallucination (SAH) | 1 | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **IH** | Identity Hallucination (IH) | 1 | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **ESH** | External Source Hallucination (ESH) | 1 | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **PCH** | Physical Constraint Hallucination (PCH) | 1 | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **CBH** | Computational Boundary Hallucination (CBH) | 1 | 1 (100.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **LDH** | Logical Deviation Hallucination (LDH) | 2 | 2 (100.0%) | 2 (100.0%) | 0 (0.0%) | 2 (100.0%) |
| **LFH** | Logical Failure Hallucination (LFH) | 2 | 2 (100.0%) | 2 (100.0%) | 0 (0.0%) | 2 (100.0%) |

### Key Architectural Findings
- **Static Categories (IH, ESH, DCH, SAH, PCH, CBH)**: SDHD achieves high coverage via SSA dominator trees and AST constraint matching, where dynamic-only methods (CodeEval, CodeHalu) cannot run without tests.
- **Dynamic Categories (LDH, LFH)**: SDHD captures subtle logical deviations and crashes via Algorithm 3 ECP/BVA test generation and iterative feedback.
- **Linters & Semantic Baselines**: PyLint and Flake8 detect identity/syntax errors (IH/LFH) but lack semantic dataflow tracking for DCH and SAH. SAC3 cosine distance flags semantic deviations but suffers high clean false positive rates.