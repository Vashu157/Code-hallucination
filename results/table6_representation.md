# Table VI: Program Representation Ablation (RQ4 Reproduction)

Compares static hallucination detection across three levels of program representation.

| Representation | Precision | Recall | F1 Score | Accuracy | FPR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| AST-only | 0.800 | 0.667 | **0.727** | 0.571 | 1.000 |
| AST+CFG | 0.800 | 0.667 | **0.727** | 0.571 | 1.000 |
| **SSA (Phase 1)** | 0.857 | 1.000 | **0.923** | 0.857 | 1.000 |

### Key Observations (RQ4)
- **AST-Only Weakness**: Lacks control-flow awareness; false positives occur on branch-scoped definitions and false negatives on reassignments.
- **AST+CFG Limitation**: While basic blocks capture branch reachability, absence of phi-functions leaves variable versions ambiguous at path join points.
- **SSA Dominance**: Full Cytron SSA construction with phi-function placement and DFS dominator renaming provides precise lifecycle tracking, maximizing F1 score.