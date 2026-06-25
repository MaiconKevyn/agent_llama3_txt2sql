## 1. Reconciliation Rules

- [x] 1.1 Add unit tests for weak scalar heuristics upgraded by valid candidate plans
- [x] 1.2 Add unit tests for explicit scalar heuristics rejecting grouped candidate plans
- [x] 1.3 Implement weak-versus-strong heuristic classification for answer shape reconciliation
- [x] 1.4 Allow safe candidate upgrades to `time_series` and `one_row_per_group` when dimensions are allowed and query evidence supports them

## 2. Metadata And Verification

- [x] 2.1 Add accepted/rejected field reasons to semantic planner metadata
- [x] 2.2 Update debug output or assertions to expose reconciliation decisions
- [x] 2.3 Add integration coverage for the original scalar-versus-time-series conflict
- [x] 2.4 Run semantic planner and reconciliation tests
