# CLAUDE.md — Contexto versionado do projeto

## Objetivo

Este arquivo agora é parte versionada do repositório. O objetivo é registrar
decisões de engenharia, contexto operacional e checkpoints relevantes sem
misturar isso com preferências locais. Overrides pessoais devem ir em
`CLAUDE.local.md`.

## Snapshot atual

- Agente principal: `LangGraphOrchestrator`
- Fluxo principal: classificação → descoberta de tabelas → schema →
  planejamento/geração SQL → validação → execução → resposta
- Modelo padrão: `gpt-4o-mini`
- Benchmark principal: `evaluation/ground_truth*.json`
- Meta atual do roadmap: CP-O1, CP-O2, CP-O5, CP-V1 concluídos; repo
  organizado e versionado; próximo passo CP-O3 (ADRs) ou Eixo 1 (Acurácia)

## Regras de manutenção

- Refactors organizacionais devem ser incrementais e com baixo risco.
- Testes, roadmap, arquitetura e ADRs devem permanecer versionados.
- Mudanças em avaliação, prompts ou roteamento precisam deixar trilha clara de
  antes/depois.
- Se um arquivo crescer demais, a extração deve preservar a API pública sempre
  que possível.

## Checkpoints

### 2026-04-30 — CP-O2 e CP-O5 concluídos

- `.gitignore` ajustado para não ignorar `CLAUDE.md`, `tests/`, `docs/`,
  `ROADMAP.md` e `ARCH.md`. `CLAUDE.local.md` definido como ignorado.
- `CP-O2` completo: orchestrator 917→550 LoC, state.py→facade (67 LoC),
  sql_generation 689→186 LoC, workflow 707→449 LoC. Módulos extraídos:
  `metrics.py`, `logging_setup.py`, `cli_session.py`, `state_models.py`,
  `state_helpers.py`, `prompt_builder.py`, `schemas.py`, `self_consistency.py`,
  `routing.py`. 53 testes passando.
- `get_llm_manager()` tornado lazy em `classification.py` e `execution.py`:
  só inicializado nos caminhos que de fato usam LLM/DB.

### 2026-02-26 — Melhorias arquiteturais históricas

- Fast-path heurístico na classificação para reduzir chamadas LLM em consultas
  claramente orientadas a banco.
- Seleção de tabelas em dois estágios com atalho heurístico de alta confiança.
- Enriquecimento do contexto de schema com mapeamentos SUS mais precisos.
- Dicas pré-geração para tabelas críticas como `socioeconomico` e
  `atendimentos`.
