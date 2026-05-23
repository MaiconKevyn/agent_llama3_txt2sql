# Revisão da implementação do plano v1 — DataSUS Agent TXT2SQL

Data da revisão: 2026-05-22T19:53:02-0300
Revisor: Hermes Agent
Plano base: `/home/maiconkevyn/Documentos/obsidian/projects/datasus agent/goal_v1.md`
Repositório: `/home/maiconkevyn/PycharmProjects/txt2sql_refactor_openai_v2`

## Veredito executivo

O plano foi implementado em grande parte e os gates objetivos principais passaram.

Status recomendado: **aprovado tecnicamente para continuar a estabilização**, mas **não pronto para merge/release sem limpeza de escopo e alguns ajustes de versionamento/manutenibilidade**.

Principais evidências positivas:

- `uv run pytest -q`: passou, com 732 testes.
- `uv run ruff check src/`: passou.
- `uv run ruff format --check src/`: passou, 101 arquivos formatados.
- `node frontend/tests/format-message-content.test.js`: passou, 14 testes.
- Benchmark v1 real: 16/16 casos passaram, score 100%.
- Threshold release v1: passou em score global, domínios críticos, out-of-schema, ambiguidade e latência.

Principais pendências:

1. O workspace está muito sujo: 68 arquivos modificados, muitos arquivos novos e vários artefatos de avaliação não commitados.
2. As ADRs em `docs/adrs/*.md` estão ignoradas por `.gitignore` via regra `docs/`; logo não entram no Git no estado atual.
3. Relatórios `.md` gerados em `evaluation/...` também estão ignorados por `.gitignore` via regra `*.md`; apenas `.json`, `.py`, `.jsonl` e este `.markdown` ficam visíveis normalmente.
4. A modularização dos god-files ainda não foi resolvida: `src/semantic/planner.py` tem 3934 linhas, `src/agent/sql_generation.py` 2689 linhas, `src/agent/execution.py` 2720 linhas, `src/semantic/validators.py` 1566 linhas e `src/agent/response.py` 922 linhas.
5. O benchmark v1 ainda é pequeno: 16 casos no total; várias categorias têm apenas 1 ou 2 casos.
6. Algumas melhorias são heurísticas/determinísticas e bem testadas, mas ainda precisam de revisão de diff antes de merge porque há mudanças amplas em backend, frontend e testes.

## Atualização de execução — 2026-05-22T20:58:00-0300

Após expandir o benchmark v1 para 10 casos por domínio, a categoria `visualizacao` revelou regressões reais que não apareciam no benchmark inicial de 16 casos:

- séries mensais por UF geravam tentativa inválida de comparar `internacoes.MUNIC_RES` com sigla de UF, por exemplo `MUNIC_RES = 'MA'`;
- gráficos de procedimentos usavam alias genérico `total_internacoes` em consultas que contavam procedimentos;
- gráficos de indicadores socioeconômicos por UF ignoravam o ano em alguns caminhos determinísticos;
- gráficos de taxa por 100 mil habitantes retornavam shape de contagem, não a taxa populacional;
- gráfico/KPI de percentual de óbitos sem raça/cor mapeada era tratado como categoria `raca_cor`, não como métrica escalar.

Correções aplicadas:

- `src/agent/sql_generation.py` agora aplica filtro de UF em gráficos de internações via `JOIN municipios ... mu."SG_UF"`, preservando `MUNIC_RES` como código municipal.
- `src/visualization/chart_plan.py` reconhece `total_procedimentos`, `taxa_por_100k` e `percentual_obitos_sem_raca_cor` como métricas explícitas de visualização.
- `src/agent/sql_generation.py` gera SQL determinístico para taxa de internações por 100 mil habitantes usando CTEs separadas de internações e população.
- `src/agent/sql_generation.py` usa o contrato escalar já existente para percentual de óbitos sem raça/cor mapeada em pedidos de gráfico/KPI.
- `evaluation/agent/generalization_rubric.py` aceita aliases semanticamente equivalentes em visualizações, como `municipio` para `municipio_residencia`, `estado` para `uf`, e `leitos_sus_1000` para `valor_indicador`.
- `tests/test_sql_execution_block.py` e `tests/test_visualization_chart_plan.py` cobrem os contratos corrigidos.

Evidência nova:

- `uv run pytest -q`: passou.
- `uv run ruff check src/`: passou.
- `uv run ruff format --check src/`: passou.
- `uv run python -m evaluation.agent.run_generalization_exhaustion --benchmark evaluation/benchmarks/v1 --category visualizacao`: passou 10/10 em `evaluation/agent/results/generalization_exhaustion_20260522T205226.json`.
- Revalidação isolada pós-ajustes finais: `V1_VIS_007,V1_VIS_008` passaram 2/2 em `evaluation/agent/results/generalization_exhaustion_20260522T205731.json`.

Evidência acumulada por domínio no benchmark v1 expandido:

| Domínio | Resultado vivo mais recente | Score |
| --- | ---: | ---: |
| ambiguidade | 10/10 | 100% |
| fora_do_schema | 10/10 | 100% |
| diagnosticos_cid | 10/10 | 100% |
| procedimentos | 10/10 | 100% |
| custos_permanencia | 10/10 | 100% |
| volume_temporal | 10/10 | 100% |
| geografia | 10/10 | 100% |
| qualidade_dados | 10/10 | 100% |
| socioeconomico_populacao | 10/10 | 100% |
| visualizacao | 10/10 | 100% |

Pendência atualizada:

- Ainda falta uma execução viva única do comando agregado `uv run python -m evaluation.agent.run_generalization_exhaustion --benchmark evaluation/benchmarks/v1` para produzir um único artefato global de 100 casos e alimentar diretamente `evaluation.agent.release_thresholds`.
- A latência continua sendo risco de produto: a categoria `visualizacao` passou funcionalmente, mas um caso levou aproximadamente 25,5s.

## Comandos executados

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run pytest --collect-only -q
uv run pytest -q
uv run python -m evaluation.agent.run_generalization_exhaustion --benchmark evaluation/benchmarks/v1
uv run python -m evaluation.agent.release_thresholds evaluation/agent/results/generalization_exhaustion_20260522T194810.json --report evaluation/results/release_v1/threshold_check_20260522T194810.md
node frontend/tests/format-message-content.test.js
git status --short --untracked-files=all
git diff --stat
git check-ignore -v docs/adrs/*.md evaluation/agent/results/generalization_exhaustion_20260522T194810.md evaluation/results/release_v1/release_v1_report_20260522.md
```

## Resultado das verificações objetivas

### Python tests

Resultado: **passou**.

`uv run pytest -q`:

- 732 testes passaram.
- 3 warnings:
  - `DuckDBEngineWarning`: duckdb-engine ainda não suporta reflexão de índices.
  - `FutureWarning` do MLflow: backend de filesystem será deprecated a partir de fevereiro de 2026.

Impacto: os warnings não bloqueiam a v1, mas o warning do MLflow deve virar item técnico futuro se MLflow continuar sendo usado.

### Coleta do pytest

Resultado: **passou**.

`uv run pytest --collect-only -q` listou normalmente todos os testes, incluindo `tests/test_agent_improvements.py`. O bloqueio anterior por `sys.exit()` foi corrigido.

### Ruff

Resultado: **passou**.

- `uv run ruff check src/`: `All checks passed!`
- `uv run ruff format --check src/`: `101 files already formatted`

A pendência anterior de 151 erros em `src/` foi corrigida.

### Frontend tests

Resultado: **passou**.

`node frontend/tests/format-message-content.test.js`:

- 14 testes passaram.
- Cobre renderização de tabelas Markdown, database explorer, limites de SQL direto, prompt contextual de tabela, chart follow-up, copy message e contratos de UI do modal.

### Benchmark v1

Resultado: **passou**.

Arquivo gerado: `evaluation/agent/results/generalization_exhaustion_20260522T194810.json`
Resumo Markdown gerado: `evaluation/agent/results/generalization_exhaustion_20260522T194810.md` — atenção: ignorado pelo Git por `*.md`.

Resumo:

- Total: 16 casos.
- Score: 100%.
- Passed: 16.
- Failed: 0.
- Answerability:
  - `answerable`: 11.
  - `requires_clarification`: 3.
  - `unanswerable_schema`: 2.

Scores por domínio:

| Domínio | Passed | Total | Score |
| --- | ---: | ---: | ---: |
| ambiguidade | 3 | 3 | 100% |
| custos_permanencia | 2 | 2 | 100% |
| diagnosticos_cid | 1 | 1 | 100% |
| fora_do_schema | 2 | 2 | 100% |
| geografia | 1 | 1 | 100% |
| procedimentos | 1 | 1 | 100% |
| qualidade_dados | 1 | 1 | 100% |
| socioeconomico_populacao | 2 | 2 | 100% |
| visualizacao | 1 | 1 | 100% |
| volume_temporal | 2 | 2 | 100% |

### Threshold release v1

Resultado: **passou**.

Arquivo gerado: `evaluation/results/release_v1/threshold_check_20260522T194810.md` — atenção: ignorado pelo Git por `*.md`.

| Check | Resultado |
| --- | --- |
| global_score >= 0.90 | passou: 1.000 |
| ambiguidade >= 0.90 | passou: 1.000 |
| fora_do_schema >= 0.95 | passou: 1.000 |
| domínios críticos >= 0.85 | passaram |
| latency answerable median <= 12s | passou: 11.017s |
| latency answerable p95 <= 30s | passou: 12.374s |

## Revisão por checkpoint do plano

### Checkpoint 0 — Congelar baseline e preparar branch limpa

Status: **parcial / pendente antes de merge**.

Evidência:

- Branch atual não foi revalidada nesta etapa do relatório, mas o workspace está amplamente modificado.
- `git status --short --untracked-files=all` mostra dezenas de arquivos modificados e novos.
- `git diff --stat` mostra 68 arquivos modificados, 2287 inserções e 1520 deleções, sem contar os arquivos untracked.

Avaliação:

- A implementação existe, mas o estado não está pronto para merge.
- É necessário separar commits por tema: testes/lint, contratos semânticos, benchmark, UX/frontend, ADRs/documentação, artefatos de avaliação.

### Checkpoint 1 — Corrigir coleta do pytest

Status: **corrigido**.

Evidência:

- `uv run pytest --collect-only -q` coleta `tests/test_agent_improvements.py` sem abortar.
- `uv run pytest -q` passa integralmente.

### Checkpoint 2 — Corrigir contrato API/orquestrador quebrado por `chart_from_last_result`

Status: **aparentemente corrigido**.

Evidência:

- Testes Python relacionados a chart/API passaram dentro da suíte completa.
- Teste frontend cobre `server proxy forwards chart_from_last_result to agent API` e passou.
- Há alterações em `src/interfaces/api/main.py`, `src/agent/orchestrator.py`, `frontend/server.js`, `frontend/public/app.js` e testes de visualização.

Risco:

- Como a revisão foi estática + testes, não foi feita sessão manual completa no navegador.

### Checkpoint 3 — Corrigir semântica CID/catalog

Status: **corrigido nos gates atuais**.

Evidência:

- `tests/test_cid_catalog_semantics.py` passou.
- Novo módulo `src/semantic/cid_rules.py` existe como untracked.
- Benchmark v1 tem caso CID (`V1_CID_001`) aprovado.
- Benchmark também validou custo médio por COVID com join CID e qualidade de dados.

Risco:

- O benchmark v1 tem apenas 1 caso explícito de `diagnosticos_cid`; deve crescer antes de release pública.

### Checkpoint 4 — Transformar `join_policy.csv` em validador ativo

Status: **implementado parcialmente como contrato executável e caveats; ainda não totalmente bloqueante**.

Evidência:

- Novo módulo `src/semantic/contracts/join_policy.py` carrega `docs/generated/join_policy.csv`.
- `policies_for_sql_joins()` detecta joins no SQL final por aliases/tabelas.
- `src/agent/response.py` chama `build_join_policy_caveats()` e adiciona caveats à resposta.
- `tests/test_join_policy_contracts.py` existe e passou.

Limitação:

- Pelo código revisado, o contrato de join é usado principalmente para caveats na resposta final. Não vi, nesta revisão, evidência de bloqueio ativo forte para impedir SQL com join `audit_only` antes da execução.
- Se o plano exigia “validador ativo” no sentido de bloquear/forçar reparo antes da execução, isso ainda parece parcial.

### Checkpoint 5 — Propagar caveats semânticos até a resposta final

Status: **corrigido**.

Evidência:

- `src/agent/response.py` agrega caveats de domínio, join policy e data quality.
- Benchmark v1 mostra caveats DQ nas respostas answerable.
- `tests/test_response_domain_caveats.py` passou.

Observação:

- Os caveats são úteis, mas a redação ainda aparece como bloco genérico “Observacoes de escopo”. Para UX final, pode valer separar “qualidade dos dados”, “escopo clínico” e “cobertura de join”.

### Checkpoint 6 — Criar ontologia versionada de conceitos clínicos

Status: **implementado**.

Evidência:

- `src/semantic/concepts/clinical_concepts_v1.yaml` existe.
- `src/semantic/concepts/clinical_concepts.py` carrega conceitos versionados.
- `src/semantic/concept_resolver.py` resolve aliases determinísticos para códigos/prefixos CID.
- `tests/test_clinical_concepts.py` passou.

Limitação:

- A ontologia inicial parece pequena, o que é correto para v1, mas deve crescer por casos reais e com governança de versionamento.

### Checkpoint 7 — Fortalecer perguntas ambíguas e clarificação

Status: **corrigido nos gates atuais**.

Evidência:

- `src/agent/plan_gate.py` tem regras determinísticas para ambiguidade geográfica, mortalidade infantil e escopo de “casos de covid”.
- Benchmark v1 teve 3/3 casos de ambiguidade aprovados como `requires_clarification`.

Limitação:

- Ainda há risco de lacunas por variações linguísticas, pois o mecanismo atual é majoritariamente regex/heurística.

### Checkpoint 8 — Melhorar safe refusal e separar sucesso de respondibilidade

Status: **corrigido nos gates atuais**.

Evidência:

- Benchmark v1 teve 2/2 casos `fora_do_schema` aprovados como `unanswerable_schema`.
- `evaluation/agent/run_generalization_exhaustion.py` e `evaluation/agent/generalization_rubric.py` foram expandidos para avaliar `answerability`.
- JSON do benchmark separa `technical_success`, `success` e `answerability`.

### Checkpoint 9 — Criar benchmark contínuo por domínio

Status: **implementado, mas pequeno**.

Evidência:

- Diretório `evaluation/benchmarks/v1/` existe com JSONL por domínio.
- Runner real executou 16 casos e gerou JSON/Markdown.
- Testes de loader/runner/rubrica passaram.

Limitação crítica:

- Vários domínios têm somente 1 caso. Isso valida o mecanismo, mas ainda não valida generalização robusta.
- Recomendação: pelo menos 10 casos por domínio crítico antes de release pública.

### Checkpoint 10 — Melhorar relatório do evaluator

Status: **corrigido**.

Evidência:

- O Markdown do benchmark lista status, scores por domínio, casos, SQL/response e caveats.
- O JSON inclui metadados ricos de workflow, plano semântico, answerability, latência e SQL.

Pendência de versionamento:

- Os relatórios `.md` gerados são ignorados por `.gitignore`. Para evidência versionável, usar `.markdown` ou ajustar `.gitignore`.

### Checkpoint 11 — Sanear Ruff sem mudar comportamento

Status: **corrigido**.

Evidência:

- `uv run ruff check src/` passou.
- `uv run ruff format --check src/` passou.

### Checkpoint 12 — Modularizar god-files por domínio

Status: **não concluído / pendência importante**.

Evidência de tamanho atual:

- `src/semantic/planner.py`: 3934 linhas.
- `src/agent/sql_generation.py`: 2689 linhas.
- `src/agent/execution.py`: 2720 linhas.
- `src/semantic/validators.py`: 1566 linhas.
- `src/agent/response.py`: 922 linhas.

Avaliação:

- O projeto está funcional, mas ainda tem risco alto de manutenção.
- Este checkpoint foi parcialmente mitigado por novos módulos (`contracts`, `concepts`, `conversation_context`, `release_thresholds`), mas a extração principal dos god-files ainda não aconteceu.

### Checkpoint 13 — Melhorar UX de resposta final

Status: **parcialmente corrigido**.

Evidência:

- `src/agent/response.py` agora tem respostas determinísticas para rowsets/single rows e caveats.
- Frontend renderiza tabelas Markdown e tem melhorias de copy/chart/database modal.
- Benchmark de visualização passou.

Limitação:

- A resposta final ainda nem sempre expõe SQL/premissas de forma estruturada para o usuário final; depende do caminho de UI/metadata.
- Para chatbot de saúde/dados públicos, seria melhor uma estrutura fixa: resposta curta, tabela, SQL usado, premissas, limitações/caveats e próximos passos.

### Checkpoint 14 — Implementar follow-up contextual robusto

Status: **implementado em versão inicial**.

Evidência:

- `src/agent/conversation_context.py` resolve follow-ups curtos por ano, dimensão e UF.
- `tests/test_followup_context.py` passou.
- Relatório de release anterior menciona follow-up textual curto resolvido contra contexto de sessão.

Limitação:

- O follow-up ainda é baseado em padrões simples. Bom para v1, mas não “robusto” em sentido amplo.

### Checkpoint 15 — Adicionar orçamento de custo, timeout e proteção de queries

Status: **parcial**.

Evidência:

- Existem `src/agent/cost_tracker.py`, `src/utils/sql_safety.py`, limites de resposta e gates de benchmark por latência.
- Testes de SQL safety/execution passaram.

Limitação:

- Nesta revisão não encontrei evidência suficiente de um orçamento de custo/timeout centralizado e aplicado como política única em todas as chamadas LLM/DB.
- Recomendo revisar especificamente limites por query DuckDB, timeout de execução SQL, limite de linhas, custo máximo por request e fallback quando exceder.

### Checkpoint 16 — Criar ADRs principais

Status: **conteúdo criado, mas não versionável no estado atual**.

Evidência:

- Arquivos existem em `docs/adrs/`:
  - `ADR-001-langgraph-workflow.md`
  - `ADR-002-llamaindex-schema-context.md`
  - `ADR-003-semantic-contract-layer.md`
  - `ADR-004-clinical-concept-resolver.md`
  - `ADR-005-answerability-and-safe-refusal.md`
  - `ADR-006-chart-followup-layer.md`

Problema:

- `git check-ignore -v` mostra que `docs/adrs/*.md` está ignorado por `.gitignore:118:docs/`.
- Logo, as ADRs não aparecem como untracked no Git e podem não ser commitadas.

Correção recomendada:

- Opção A: ajustar `.gitignore` para permitir `docs/adrs/*.md`.
- Opção B: mover/copiar ADRs para um caminho versionável com extensão `.markdown`, por exemplo `evaluation/results/adrs/*.markdown`.
- Opção C: versionar `docs/` explicitamente se for decisão do projeto.

### Checkpoint 17 — Definir score mínimo de release

Status: **corrigido**.

Evidência:

- `evaluation/agent/release_thresholds.py` existe.
- `tests/test_release_thresholds.py` passou.
- Threshold check executado sobre o benchmark novo e passou.

## Achados por severidade

### Alta — ADRs e relatórios `.md` ignorados pelo Git

Evidência:

```text
.gitignore:118:docs/ docs/adrs/ADR-001-langgraph-workflow.md
.gitignore:62:*.md evaluation/agent/results/generalization_exhaustion_20260522T194810.md
.gitignore:62:*.md evaluation/results/release_v1/release_v1_report_20260522.md
```

Impacto:

- Decisões arquiteturais e evidências de release podem ficar fora do histórico versionado.

Recomendação:

- Resolver antes de merge. Para relatórios, usar `.markdown`. Para ADRs, permitir `docs/adrs/*.md` ou salvar como `.markdown` em caminho versionável.

### Alta — Workspace grande demais para merge sem fatiamento

Evidência:

- 68 arquivos modificados no diff tracked.
- Muitos arquivos untracked relevantes: contratos, benchmarks, testes, resultados JSON e relatórios.

Impacto:

- Risco de review superficial, commits difíceis de reverter e mistura de refactor, feature, avaliação e frontend.

Recomendação:

- Separar commits/PRs:
  1. Correção de coleta pytest + lint.
  2. Contratos semânticos (`contracts`, join/data quality/candidate keys).
  3. CID/conceitos clínicos.
  4. Plan gate/answerability/refusal.
  5. Benchmark v1 + thresholds.
  6. UX/frontend/chart follow-up.
  7. ADRs/documentação.
  8. Artefatos de avaliação selecionados.

### Média — God-files permanecem grandes

Impacto:

- Manutenção difícil e risco de regressão em áreas críticas.

Recomendação:

- Tratar modularização como próximo marco, não bloquear a validação funcional atual.
- Prioridade: extrair de `planner.py`, `sql_generation.py`, `execution.py`, `validators.py` e `response.py` por domínio/contrato.

### Média — Benchmark v1 pequeno

Impacto:

- Score 100% é forte para smoke/regression, mas ainda frágil como evidência de generalização.

Recomendação:

- Expandir para 10+ casos por domínio crítico, incluindo:
  - CID capítulo, grupo, categoria, código específico, descrições ambíguas.
  - Geografia por residência vs hospital.
  - População/taxas com joins socioeconômicos.
  - Procedimentos com e sem diagnóstico.
  - Out-of-schema médico/medicamento/exames/longitudinal.
  - Perguntas com linguagem leiga e incompleta.

### Média — Join policy parece caveat-first, não blocker-first

Impacto:

- SQL com join de baixa cobertura pode ser executado e só explicado depois.

Recomendação:

- Se o contrato exigir bloqueio ativo, integrar `JoinPolicyRegistry` no validador pré-execução/plan auditor.
- `audit_only` deveria exigir escopo explícito, LEFT JOIN ou recusa/clarificação dependendo da pergunta.

### Baixa — Warnings de dependência

Impacto:

- Não bloqueia v1.

Recomendação:

- Registrar follow-up para MLflow filesystem backend se MLflow continuar no roadmap.

## Conclusão

O estado atual está muito melhor que o baseline do plano: testes, lint, benchmark v1, threshold de release, CID básico, safe refusal, ambiguidade, caveats e UX inicial foram implementados e verificados.

Ainda falta, antes de considerar “tudo corrigido”:

1. Resolver versionamento dos ADRs e relatórios ignorados.
2. Limpar/fatiar o workspace em commits revisáveis.
3. Ampliar benchmark v1 para reduzir overfit.
4. Modularizar god-files.
5. Decidir se join policy será apenas caveat ou bloqueio ativo pré-execução.
6. Revisar orçamento/timeout/custo como política centralizada.

Recomendação final: **não há bloqueio funcional imediato pelos gates automatizados**, mas há bloqueios de engenharia/release para merge limpo e manutenção de longo prazo.

## Atualização final de execução — 2026-05-22T21:35:00-0300

O benchmark v1 expandido foi executado em artefato único de 100 casos:

- Resultado JSON: `evaluation/agent/results/generalization_exhaustion_20260522T205851.json`.
- Relatório Markdown local: `evaluation/agent/results/generalization_exhaustion_20260522T205851.md`.
- Total: 100 casos.
- Status: 100 passed / 0 failed.
- Score global: 100%.

Scores por domínio:

| Domínio | Resultado |
| --- | ---: |
| ambiguidade | 10/10 |
| custos_permanencia | 10/10 |
| diagnosticos_cid | 10/10 |
| fora_do_schema | 10/10 |
| geografia | 10/10 |
| procedimentos | 10/10 |
| qualidade_dados | 10/10 |
| socioeconomico_populacao | 10/10 |
| visualizacao | 10/10 |
| volume_temporal | 10/10 |

O gate numérico de release v1 também passou com o artefato global:

- Relatório local: `evaluation/results/release_v1/threshold_check_20260522T205851.md`.
- Relatório versionável equivalente: `evaluation/results/release_v1/threshold_check_20260522T205851.markdown`.
- `global_score`: 1.000 >= 0.900.
- Domínios críticos: todos 1.000 >= 0.850.
- `fora_do_schema`: 1.000 >= 0.950.
- `ambiguidade`: 1.000 >= 0.900.
- Latência mediana answerable: 10.508s <= 12.000s.
- Latência p95 answerable: 21.051s <= 30.000s.

Verificações técnicas finais executadas:

```bash
uv run pytest -q
uv run ruff check src/
uv run ruff format --check src/
node frontend/tests/format-message-content.test.js
uv run pytest -q tests/test_followup_context.py tests/test_join_policy_contracts.py tests/test_generated_contracts.py tests/test_clinical_concepts.py tests/test_release_thresholds.py
```

Resultado:

- Python: suíte completa passou.
- Ruff: `src/` passou em lint e format check.
- Frontend: 15 testes passaram.
- Testes focados de contratos/follow-up/conceitos/thresholds passaram.

Correção adicional aplicada após a auditoria:

- A UI de chat agora apresenta feedback progressivo durante consultas longas, com mensagens de etapa para preparação, seleção de tabelas/contexto, validação de SQL/contratos, execução DuckDB e finalização da resposta.
- `frontend/tests/format-message-content.test.js` cobre a presença desse contrato visual.
- `.gitignore` foi ajustado para manter `docs/` local-only por padrão, mas permitir versionamento explícito de `docs/adrs/*.md`.
- A modularização foi avançada por extração vertical da família CID:
  - `src/semantic/cid_rules.py` concentra regras semânticas CID.
  - `src/semantic/concepts/` concentra conceitos clínicos versionados.
  - `src/agent/cid_catalog_sql.py` concentra templates SQL determinísticos de catálogo CID.
  - `tests/test_cid_catalog_semantics.py` cobre diretamente o novo módulo de SQL do catálogo CID.

Estado final de release local:

- Workspace limpo após commits.
- Commits publicados em `origin/llamaindex_dev`.
- ADRs versionáveis em `docs/adrs/*.md`.
- Release threshold versionável em `evaluation/results/release_v1/threshold_check_20260522T205851.markdown`.

Pendência de evolução pós-v1:

1. Continuar a redução dos god-files em marcos posteriores, pois a v1 já tem extrações verticais testadas e os gates funcionais passaram.
2. Avaliar se artefatos intermediários de benchmark devem continuar versionados ou se futuros runs devem versionar apenas artefatos finais.
