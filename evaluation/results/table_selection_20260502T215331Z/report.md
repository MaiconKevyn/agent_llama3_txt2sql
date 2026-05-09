# Table Selection Benchmark Report

- **Date**: 2026-05-02T21:56:02.009831+00:00
- **Queries per variant**: 40

## Summary

| ID | Variant | Raw Acceptable | Validated Acceptable | Raw Core Recall | Validated Core Recall | Raw Precision | Validated Precision | Avg Selected |
|---|---|---|---|---|---|---|---|---|
| TS00 | llm_only::role_guardrails::decision_checklist | 87.5% | 92.5% | 99.2% | 99.2% | 96.9% | 98.5% | 1.77 |
| TS01 | llm_only::role_guardrails::selection_protocol | 90.0% | 90.0% | 99.2% | 99.2% | 97.7% | 97.7% | 1.80 |
| TS02 | llm_only::role_guardrails::decision_protocol | 85.0% | 90.0% | 98.3% | 98.3% | 96.9% | 98.5% | 1.75 |
| TS04 | llm_only::schema_contract::selection_protocol | 87.5% | 90.0% | 98.3% | 98.3% | 97.3% | 98.5% | 1.75 |
| TS03 | llm_only::schema_contract::decision_checklist | 80.0% | 87.5% | 97.9% | 97.9% | 95.0% | 97.9% | 1.77 |
| TS05 | llm_only::schema_contract::decision_protocol | 85.0% | 87.5% | 97.9% | 97.9% | 96.9% | 97.7% | 1.77 |

## Failure Samples

### TS00 llm_only::role_guardrails::decision_checklist

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS01 llm_only::role_guardrails::selection_protocol

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT118` stage=`llm` selected=["internacoes", "hospital", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["municipios"] forbidden=[]

### TS02 llm_only::role_guardrails::decision_protocol

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS04 llm_only::schema_contract::selection_protocol

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS03 llm_only::schema_contract::decision_checklist

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["atendimentos", "procedimentos", "internacoes", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT086` stage=`llm` selected=["internacoes", "hospital", "socioeconomico", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]

### TS05 llm_only::schema_contract::decision_protocol

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT118` stage=`llm` selected=["internacoes", "hospital", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["municipios"] forbidden=[]
