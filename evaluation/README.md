# Text-to-SQL Datasus Agent Evaluation

Evaluation of Text-to-SQL agent performance on Brazilian healthcare data (DATASUS/SIH-RS) using LLaMA 3.1:8b.

## Overview

**Dataset**: 59 ground truth queries across three difficulty levels
- EASY (25): Single table, basic filters, COUNT operations
- MEDIUM (19): Multi-table JOINs, GROUP BY, aggregations
- HARD (15): Complex JOINs, subqueries, mortality calculations

**Model**: Ollama LLaMA 3.1:8b
**Evaluation Date**: November 3, 2025
**Total Execution Time**: 531.1s (9.0s avg per query)

## Evaluation Metrics

Three metrics following Spider benchmark methodology:

**Execution Accuracy (EX)** - Primary metric
- Percentage of queries returning correct results
- Threshold: Score ≥ 0.8 considered correct
- Most critical indicator of agent performance

**Component Matching (CM)**
- Structural similarity between generated and ground truth SQL
- Components: SELECT, FROM, WHERE, GROUP BY, ORDER BY, JOIN, nested queries
- Measures semantic understanding despite different formulation

**Exact Match (EM)**
- Binary match between generated and ground truth SQL
- Least critical - multiple valid SQL queries can produce same results

## Results

### Summary

| Metric | Score |
|--------|-------|
| Agent Success Rate | 100.0% |
| Execution Accuracy (EX) | 81.6% |
| Component Matching (CM) | 61.6% |
| Exact Match (EM) | 16.9% |

High EX (81.6%) with low EM (16.9%) indicates the agent generates semantically correct but syntactically different SQL queries.

---

## Performance Analysis

### By Difficulty Level

| Difficulty | Questions | Success Rate | EX | CM | EM |
|-----------|-----------|--------------|----|----|-----|
| EASY | 25 | 100.0% (25/25) | 96.0% | 75.0% | 16.0% |
| MEDIUM | 19 | 100.0% (19/19) | 78.9% | 61.1% | 15.8% |
| HARD | 15 | 100.0% (15/15) | 60.0% | 43.3% | 6.7% |

### Performance by Query Complexity

**EASY Queries**
- Excellent execution accuracy (96.0%)
- Strong component matching (75.0%)
- Covers: Single table operations, basic filtering, COUNT aggregations, MIN/MAX operations

**MEDIUM Queries**
- Good execution accuracy (78.9%)
- Moderate component matching (61.1%)
- Covers: Multi-table JOINs, GROUP BY operations, temporal filters

**HARD Queries**
- Moderate execution accuracy (60.0%)
- Lower component matching (43.3%)
- Covers: Mortality rate calculations, nested subqueries, complex temporal analysis

---

## Visualizations

### Metrics Comparison

![Metrics Comparison](results/visualizations/metrics_comparison.png)

Shows EX (81.6%) significantly exceeds EM (16.9%), indicating semantically correct but syntactically different SQL generation.

### Performance by Difficulty

![Difficulty Breakdown](results/visualizations/difficulty_breakdown.png)

Demonstrates performance degradation with increasing complexity. Gap between EX and EM widens for HARD queries.

### Success Rate Distribution

![Success Rate](results/visualizations/success_rate.png)

Overall success rate: 100.0% (59/59 queries). Distribution shows strong performance across all difficulty levels.

---

## Discussion

### Key Findings

**Strengths**
- High execution accuracy (81.6%) demonstrates correct result generation
- Excellent performance on EASY queries (96.0% EX)
- Perfect agent success rate (100.0%) with zero failures
- Component matching (61.6%) indicates semantic SQL understanding
- Improved dataset with 59 ground truth queries (up from 51)

**Limitations**
- HARD query performance (60.0% EX) requires improvement
- Low exact match (16.9%) reflects syntactic variations from ground truth
- Complex mortality rate calculations remain challenging
- Nested subqueries and multi-table temporal joins show higher error rates

### Analysis

**Low EM with High EX**

The disparity between EM (16.9%) and EX (81.6%) is expected and indicates SQL flexibility. Multiple syntactically different queries can produce identical results.

Example:
```sql
-- Ground Truth (EM = 0)
SELECT COUNT(*) FROM internacoes i
LEFT JOIN mortes m ON i."N_AIH" = m."N_AIH"
WHERE m."N_AIH" IS NULL

-- Agent Generated (EX = 1, EM = 0, CM = 0.7)
SELECT COUNT(*) FROM internacoes
WHERE "N_AIH" NOT IN (SELECT "N_AIH" FROM mortes)
```

Both queries return identical results despite different formulations.

**HARD Query Error Patterns**

Analysis reveals systematic challenges:
- Mortality rate calculations requiring percentage operations
- Multi-table temporal JOINs with complex date filtering
- Nested aggregations within subqueries
- CID-10 disease code pattern matching

## Running Evaluation

```bash
# Run full evaluation
python evaluation/run_dag_evaluation.py

# Run by difficulty level
python evaluation/run_dag_evaluation.py --difficulty EASY

# Generate visualizations and report
python evaluation/generate_report.py
```

### Output Files

```
evaluation/agent/results/
evaluation/ablation/results/
evaluation/table_selection/results/
├── dag_evaluation_YYYYMMDD_HHMMSS.json      # Raw data
├── dag_evaluation_report_YYYYMMDD_HHMMSS.txt # Summary
├── EVALUATION_REPORT.txt                     # Full analysis
└── visualizations/
    ├── metrics_comparison.png
    ├── difficulty_breakdown.png
    ├── success_rate.png
    └── metric_distributions.png
```

---

## Architecture

```
evaluation/
├── dag/                       # DAG pipeline implementation
├── metrics/                  # EM, CM, EX implementations
├── ground_truth.json         # Ground truth queries (59 queries)
├── run_dag_evaluation.py     # Evaluation runner
└── generate_report.py        # Report generator
```
