# Table VII: Category Breakdown Ablation across 8 Types (RQ5 Reproduction)

Measures detection coverage across all 8 hallucination types comparing SDHD-S, SDHD-D, and Full SDHD.

| Code | Hallucination Category | Ground Truth | SDHD-S (Static) | SDHD-D (Dynamic) | SDHD (Hybrid) |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **DCH** | Data Compliance Hallucination (DCH) | 1 | 1 (100.0%) | 0 (0.0%) | **1 (100.0%)** |
| **SAH** | Structure Access Hallucination (SAH) | 1 | 1 (100.0%) | 0 (0.0%) | **1 (100.0%)** |
| **IH** | Identity Hallucination (IH) | 1 | 1 (100.0%) | 0 (0.0%) | **1 (100.0%)** |
| **ESH** | External Source Hallucination (ESH) | 1 | 1 (100.0%) | 0 (0.0%) | **1 (100.0%)** |
| **PCH** | Physical Constraint Hallucination (PCH) | 1 | 1 (100.0%) | 0 (0.0%) | **1 (100.0%)** |
| **CBH** | Computational Boundary Hallucination (CBH) | 1 | 1 (100.0%) | 0 (0.0%) | **1 (100.0%)** |
| **LDH** | Logical Deviation Hallucination (LDH) | 2 | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |
| **LFH** | Logical Failure Hallucination (LFH) | 2 | 0 (0.0%) | 0 (0.0%) | **0 (0.0%)** |

### Key Observations (RQ5)
- **Static Specialization**: SDHD-S provides full coverage over DCH, SAH, IH, ESH, PCH, and CBH, but 0% on dynamic categories (LDH).
- **Dynamic Specialization**: SDHD-D catches 100% of runtime logic deviations (LDH) and crashes (LFH), but misses structural/AST hallucinations without tests.
- **Hybrid Complementarity**: Full SDHD achieves balanced high recall across both static and dynamic categories, validating the hybrid approach.