# Table Selection Benchmark Report

- **Date**: 2026-05-02T21:46:56.969691+00:00
- **Queries per variant**: 40

## Summary

| ID | Variant | Raw Acceptable | Validated Acceptable | Raw Core Recall | Validated Core Recall | Raw Precision | Validated Precision | Avg Selected |
|---|---|---|---|---|---|---|---|---|
| TS22 | llm_only::role_guardrails::decision_checklist | 87.5% | 92.5% | 99.2% | 99.2% | 96.9% | 98.5% | 1.77 |
| TS23 | llm_only::role_guardrails::selection_protocol | 90.0% | 90.0% | 99.2% | 99.2% | 97.7% | 97.7% | 1.80 |
| TS35 | llm_only::schema_contract::selection_protocol | 87.5% | 90.0% | 98.3% | 98.3% | 97.3% | 98.5% | 1.75 |
| TS21 | llm_only::role_guardrails::anti_overselection | 87.5% | 90.0% | 97.9% | 97.9% | 97.7% | 98.5% | 1.75 |
| TS33 | llm_only::schema_contract::anti_overselection | 87.5% | 90.0% | 97.9% | 97.9% | 97.3% | 98.5% | 1.75 |
| TS18 | llm_only::role_guardrails::current | 82.5% | 87.5% | 97.9% | 99.2% | 94.4% | 96.5% | 1.82 |
| TS19 | llm_only::role_guardrails::compact | 77.5% | 87.5% | 97.1% | 98.3% | 93.3% | 97.3% | 1.77 |
| TS34 | llm_only::schema_contract::decision_checklist | 80.0% | 87.5% | 97.9% | 97.9% | 95.0% | 97.9% | 1.77 |
| TS31 | llm_only::schema_contract::compact | 77.5% | 87.5% | 95.8% | 97.1% | 94.4% | 98.5% | 1.73 |
| TS17 | llm_only::use_cases::selection_protocol | 85.0% | 87.5% | 96.7% | 96.7% | 93.5% | 94.8% | 1.80 |
| TS20 | llm_only::role_guardrails::minimal | 80.0% | 85.0% | 97.5% | 98.3% | 94.2% | 96.0% | 1.80 |
| TS10 | llm_only::minimal::decision_checklist | 70.0% | 80.0% | 97.5% | 97.5% | 89.8% | 95.2% | 1.80 |
| TS16 | llm_only::use_cases::decision_checklist | 75.0% | 80.0% | 97.1% | 97.1% | 93.1% | 95.2% | 1.80 |
| TS30 | llm_only::schema_contract::current | 75.0% | 80.0% | 95.8% | 97.1% | 93.1% | 95.2% | 1.80 |
| TS32 | llm_only::schema_contract::minimal | 72.5% | 80.0% | 96.2% | 96.2% | 93.1% | 96.0% | 1.75 |
| TS15 | llm_only::use_cases::anti_overselection | 72.5% | 80.0% | 95.8% | 95.8% | 91.0% | 94.0% | 1.82 |
| TS12 | llm_only::use_cases::current | 70.0% | 77.5% | 99.2% | 99.2% | 87.7% | 91.0% | 1.95 |
| TS27 | llm_only::join_paths::anti_overselection | 72.5% | 77.5% | 98.3% | 98.3% | 89.8% | 92.3% | 1.88 |
| TS09 | llm_only::minimal::anti_overselection | 72.5% | 77.5% | 97.9% | 97.9% | 89.0% | 91.0% | 1.93 |
| TS03 | llm_only::current::anti_overselection | 72.5% | 77.5% | 96.2% | 96.2% | 93.5% | 95.6% | 1.77 |
| TS06 | llm_only::minimal::current | 70.0% | 75.0% | 99.2% | 99.2% | 89.4% | 89.8% | 2.02 |
| TS24 | llm_only::join_paths::current | 65.0% | 75.0% | 97.1% | 98.3% | 87.3% | 90.4% | 2.02 |
| TS28 | llm_only::join_paths::decision_checklist | 62.5% | 75.0% | 97.5% | 97.5% | 86.0% | 91.2% | 1.95 |
| TS11 | llm_only::minimal::selection_protocol | 72.5% | 75.0% | 96.7% | 96.7% | 87.3% | 87.7% | 2.08 |
| TS00 | llm_only::current::current | 67.5% | 72.5% | 98.3% | 98.3% | 88.1% | 89.8% | 1.95 |
| TS13 | llm_only::use_cases::compact | 65.0% | 72.5% | 96.2% | 96.2% | 89.0% | 92.7% | 1.82 |
| TS05 | llm_only::current::selection_protocol | 70.0% | 72.5% | 95.8% | 95.8% | 88.1% | 89.4% | 1.90 |
| TS29 | llm_only::join_paths::selection_protocol | 67.5% | 70.0% | 95.8% | 95.8% | 86.9% | 86.0% | 2.10 |
| TS14 | llm_only::use_cases::minimal | 60.0% | 67.5% | 98.3% | 98.3% | 83.1% | 85.6% | 2.10 |
| TS07 | llm_only::minimal::compact | 55.0% | 67.5% | 97.5% | 97.5% | 81.0% | 86.8% | 2.08 |
| TS04 | llm_only::current::decision_checklist | 62.5% | 67.5% | 96.2% | 96.2% | 88.5% | 90.6% | 1.88 |
| TS01 | llm_only::current::compact | 50.0% | 60.0% | 97.5% | 97.5% | 79.8% | 85.2% | 2.05 |
| TS02 | llm_only::current::minimal | 52.5% | 60.0% | 97.5% | 97.5% | 81.2% | 84.6% | 2.08 |
| TS25 | llm_only::join_paths::compact | 50.0% | 60.0% | 96.2% | 96.2% | 77.7% | 82.5% | 2.23 |
| TS08 | llm_only::minimal::minimal | 55.0% | 60.0% | 95.8% | 95.8% | 80.6% | 81.9% | 2.10 |
| TS26 | llm_only::join_paths::minimal | 47.5% | 55.0% | 96.2% | 96.2% | 76.7% | 78.8% | 2.30 |

## Failure Samples

### TS22 llm_only::role_guardrails::decision_checklist

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["atendimentos", "procedimentos", "internacoes", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS23 llm_only::role_guardrails::selection_protocol

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT118` stage=`llm` selected=["internacoes", "hospital", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["municipios"] forbidden=[]

### TS35 llm_only::schema_contract::selection_protocol

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS21 llm_only::role_guardrails::anti_overselection

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS33 llm_only::schema_contract::anti_overselection

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS18 llm_only::role_guardrails::current

- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]
- `GT088` stage=`llm` selected=["internacoes", "hospital", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["hospital"] forbidden=[]

### TS19 llm_only::role_guardrails::compact

- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["atendimentos", "procedimentos", "internacoes", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT086` stage=`llm` selected=["internacoes", "hospital"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS34 llm_only::schema_contract::decision_checklist

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["atendimentos", "procedimentos", "internacoes", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT086` stage=`llm` selected=["internacoes", "hospital", "socioeconomico", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]

### TS31 llm_only::schema_contract::compact

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT086` stage=`llm` selected=["internacoes", "hospital"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS17 llm_only::use_cases::selection_protocol

- `GT040` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["socioeconomico"] unexpected=["internacoes"] forbidden=["internacoes"]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS20 llm_only::role_guardrails::minimal

- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["atendimentos", "procedimentos", "sexo", "internacoes"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS10 llm_only::minimal::decision_checklist

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "socioeconomico"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS16 llm_only::use_cases::decision_checklist

- `GT007` stage=`llm` selected=["internacoes", "hospital"] raw_ok=False validated_ok=False missing=[] unexpected=["hospital"] forbidden=[]
- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "socioeconomico"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]

### TS30 llm_only::schema_contract::current

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT083` stage=`llm` selected=["internacoes", "instrucao"] raw_ok=False validated_ok=False missing=["municipios"] unexpected=[] forbidden=[]

### TS32 llm_only::schema_contract::minimal

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "sexo", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS15 llm_only::use_cases::anti_overselection

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT078` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=["cid"] unexpected=["atendimentos", "procedimentos"] forbidden=[]

### TS12 llm_only::use_cases::current

- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "socioeconomico"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS27 llm_only::join_paths::anti_overselection

- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT037` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS09 llm_only::minimal::anti_overselection

- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]

### TS03 llm_only::current::anti_overselection

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]
- `GT081` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS06 llm_only::minimal::current

- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT067` stage=`llm` selected=["internacoes", "atendimentos", "especialidade", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]

### TS24 llm_only::join_paths::current

- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT067` stage=`llm` selected=["internacoes", "atendimentos", "especialidade", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]

### TS28 llm_only::join_paths::decision_checklist

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "socioeconomico"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]
- `GT076` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["hospital"] unexpected=[] forbidden=[]

### TS11 llm_only::minimal::selection_protocol

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT040` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["socioeconomico"] unexpected=["internacoes", "municipios"] forbidden=["internacoes"]
- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "cid", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "cid", "procedimentos"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS00 llm_only::current::current

- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT037` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "hospital", "socioeconomico"] raw_ok=False validated_ok=False missing=[] unexpected=["hospital", "socioeconomico"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS13 llm_only::use_cases::compact

- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT037` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=[] unexpected=["municipios"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "socioeconomico"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS05 llm_only::current::selection_protocol

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT040` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["socioeconomico"] unexpected=["internacoes"] forbidden=["internacoes"]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "hospital"] raw_ok=False validated_ok=False missing=[] unexpected=["hospital"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS29 llm_only::join_paths::selection_protocol

- `GT007` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT040` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["socioeconomico"] unexpected=["internacoes", "municipios"] forbidden=["internacoes"]
- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS14 llm_only::use_cases::minimal

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "socioeconomico", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico", "tempo"] forbidden=[]
- `GT046` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS07 llm_only::minimal::compact

- `GT007` stage=`llm` selected=["internacoes", "atendimentos", "especialidade", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "especialidade", "procedimentos"] forbidden=[]
- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "socioeconomico"] raw_ok=False validated_ok=False missing=[] unexpected=["socioeconomico"] forbidden=[]

### TS04 llm_only::current::decision_checklist

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT014` stage=`llm` selected=["internacoes"] raw_ok=False validated_ok=False missing=["cid"] unexpected=[] forbidden=[]
- `GT023` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
- `GT044` stage=`llm` selected=["internacoes", "hospital"] raw_ok=False validated_ok=False missing=[] unexpected=["hospital"] forbidden=[]

### TS01 llm_only::current::compact

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT023` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT037` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS02 llm_only::current::minimal

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT023` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT037` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "sexo", "cid"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS25 llm_only::join_paths::compact

- `GT007` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT037` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]

### TS08 llm_only::minimal::minimal

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT017` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT040` stage=`llm` selected=["internacoes", "municipios"] raw_ok=False validated_ok=False missing=["socioeconomico"] unexpected=["internacoes", "municipios"] forbidden=["internacoes"]
- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]

### TS26 llm_only::join_paths::minimal

- `GT007` stage=`llm` selected=["internacoes", "especialidade"] raw_ok=False validated_ok=False missing=[] unexpected=["especialidade"] forbidden=[]
- `GT023` stage=`llm` selected=["internacoes", "atendimentos", "procedimentos"] raw_ok=False validated_ok=False missing=[] unexpected=["atendimentos", "procedimentos"] forbidden=[]
- `GT036` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT037` stage=`llm` selected=["internacoes", "tempo"] raw_ok=False validated_ok=False missing=[] unexpected=["tempo"] forbidden=[]
- `GT039` stage=`llm` selected=["internacoes", "cid", "sexo"] raw_ok=False validated_ok=False missing=[] unexpected=["sexo"] forbidden=[]
