## 1. Repair Candidate Evaluation

- [x] 1.1 Add tests for repair candidates that preserve required semantic answer shape
- [x] 1.2 Add tests rejecting diagnosis lookup repair for chart/time-series requests when chart columns are missing
- [x] 1.3 Implement repair candidate validation against semantic shape and chart required columns before accepting a repair
- [x] 1.4 Rank deterministic repair candidates by contract fit instead of first non-null SQL

## 2. Diagnostics And Regression

- [x] 2.1 Add metadata for accepted and rejected repair candidates
- [x] 2.2 Improve final error messaging when no candidate can preserve the requested shape
- [x] 2.3 Add regression coverage for diagnosis validation followed by chart-plan repair
- [x] 2.4 Run semantic repair, chart validation, and original failing-query regression tests
