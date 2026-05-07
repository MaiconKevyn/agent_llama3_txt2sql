# Table Selection Benchmark Report

- **Date**: 2026-05-02T22:01:31.743366+00:00
- **Queries per variant**: 40

## Summary

| ID | Variant | Raw Acceptable | Validated Acceptable | Raw Core Recall | Validated Core Recall | Raw Precision | Validated Precision | Avg Selected |
|---|---|---|---|---|---|---|---|---|
| TS00 | llm_only::role_guardrails::decision_checklist | 87.5% | 100.0% | 99.2% | 100.0% | 96.9% | 100.0% | 1.75 |
| TS01 | llm_only::role_guardrails::selection_protocol | 90.0% | 97.5% | 99.2% | 100.0% | 97.7% | 99.2% | 1.77 |
| TS02 | llm_only::role_guardrails::decision_protocol | 85.0% | 97.5% | 98.3% | 99.2% | 96.9% | 100.0% | 1.73 |
| TS04 | llm_only::schema_contract::selection_protocol | 87.5% | 97.5% | 98.3% | 99.2% | 97.3% | 100.0% | 1.73 |
| TS03 | llm_only::schema_contract::decision_checklist | 80.0% | 95.0% | 97.9% | 98.8% | 95.0% | 99.4% | 1.75 |
| TS05 | llm_only::schema_contract::decision_protocol | 80.0% | 92.5% | 97.1% | 97.9% | 95.6% | 99.2% | 1.73 |

## Failure Samples

### TS01 llm_only::role_guardrails::selection_protocol

- `GT118` stage=`llm` selected=["internacoes", "hospital", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["municipios"] forbidden=[]

### TS02 llm_only::role_guardrails::decision_protocol

- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS04 llm_only::schema_contract::selection_protocol

- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS03 llm_only::schema_contract::decision_checklist

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT086` stage=`llm` selected=["internacoes", "hospital", "socioeconomico", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]

### TS05 llm_only::schema_contract::decision_protocol

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]
- `GT118` stage=`llm` selected=["internacoes", "hospital", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["municipios"] forbidden=[]
