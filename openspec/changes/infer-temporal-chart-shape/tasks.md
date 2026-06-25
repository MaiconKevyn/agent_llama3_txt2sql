## 1. Detection And Contracts

- [x] 1.1 Add tests for explicit year-list extraction from chart and non-chart prompts
- [x] 1.2 Implement a shared helper that detects two or more explicit years without converting non-contiguous lists to ranges
- [x] 1.3 Update chart planning to produce `line`, `x_dimension=ano`, `time_metric`, and required columns for explicit-year chart requests
- [x] 1.4 Update semantic planning to include `ano` as an output dimension for supported explicit-year chart requests

## 2. Regression Coverage

- [x] 2.1 Add tests proving scalar total prompts across multiple years remain scalar
- [x] 2.2 Add tests proving explicit-year chart prompts allow `GROUP BY ano`
- [x] 2.3 Add an end-to-end CLI or orchestrator regression for the respiratory deaths chart prompt
- [x] 2.4 Run targeted planner/chart tests and one full relevant regression command
