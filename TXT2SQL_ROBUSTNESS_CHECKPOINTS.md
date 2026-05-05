# Roadmap Consolidado de Robustez Text-to-SQL

Data de criacao: 2026-05-05

Este arquivo consolida os checkpoints de curto, medio e longo prazo para evoluir o agente Text-to-SQL com foco em generalizacao, compreensao da base e confiabilidade semantica. O plano foi definido a partir da premissa de que o objetivo nao e tunar o comportamento para o ground truth atual nem criar vies de benchmark.

Arquivos de tracking detalhado:

- `SHORT_TERM_CHECKPOINTS.md`
- `MEDIUM_LONG_TERM_CHECKPOINTS.md`

## Objetivo central

Melhorar o agente para responder bem perguntas gerais sobre a base de dados, especialmente hard queries, sem otimizar artificialmente apenas `execution accuracy`.

## Problemas semanticos alvo

- Output shape incorreto.
- Top-N por grupo versus top-N global.
- Denominadores errados em taxas.
- Comparacoes temporais e deltas.
- Anti-condicoes como "nunca", "sem registro", "nenhuma ocorrencia".
- Regras implicitas de negocio.
- Granularidade de fatos versus dimensoes.
- Agrupamento incorreto.
- Interpretacao incorreta de codigos e dominios.
- Confusao entre residencia do paciente e localizacao do hospital.

## Principios de generalizacao

- Regras devem ser por classe semantica, nao por pergunta.
- Catalogo semantico deve ser baseado no dominio, nao no benchmark.
- Validacao deve verificar intencao e shape, nao apenas sintaxe.
- Avaliacao deve separar EX, semantica, plano, SQL, execucao e resposta final.
- Mudancas devem ser acompanhadas de testes adversariais fora do ground truth.
- Prompts, validadores e catalogos runtime nao devem conter IDs, perguntas literais ou respostas esperadas do benchmark.

## Curto Prazo - Status concluido

Arquivo detalhado: `SHORT_TERM_CHECKPOINTS.md`

### C1 - Semantic plan antes da SQL

Status: concluido

Resultado:

- Criados modelos tipados para `SemanticPlan`.
- Criado planner heuristico generico.
- Plano armazenado no state.

Impacto:

- O agente passa a ter contrato explicito de intent, metricas, dimensoes, filtros, shape e constraints antes da SQL.

### C2 - Injecao do semantic plan no prompt SQL

Status: concluido

Resultado:

- O plano semantico e renderizado e injetado na geracao SQL.

Impacto:

- Reduz SQLs que ignoram shape esperado, denominador e regras de ausencia.

### C3 - Validacao semantica da SQL

Status: concluido

Resultado:

- Validador bloqueia top-N por grupo sem janela, taxa com denominador filtrado, anti-condicao sem anti-join/aggregate-zero e bucket desconhecido sem politica explicita.

Impacto:

- SQL executavel mas semanticamente errada passa a ser rejeitada antes da execucao final.

### C4 - Defaults de table selection sem mascarar preset

Status: concluido

Resultado:

- Defaults do CLI/config nao sobrescrevem `llm_best`.

Impacto:

- Table selection usa o preset esperado em vez de cair em configuracao antiga.

### C5 - Observabilidade do workflow real

Status: concluido

Resultado:

- CLI corrigido.
- Debug mostra `semantic_plan`.

Impacto:

- Permite validar comportamento real por etapa.

### C6 - Validacao real em hard queries

Status: concluido

Resultado:

- Testado top-N por grupo, taxa com denominador e anti-condicao via CLI real.

Impacto:

- Evidencia pratica de melhora nas classes de falha mais relevantes.

### C7 - Resposta final fiel ao resultado

Status: concluido

Resultado:

- Prompt de resposta preserva identificadores como `CNES`.
- Lista longa limitada.

Impacto:

- Reduz alucinacao na etapa final de resposta.

### C8 - Guardrails contra benchmark hacking

Status: concluido

Resultado:

- Sem IDs de ground truth, perguntas especificas ou valores esperados no runtime.

Impacto:

- Reduz risco de ajuste artificial ao benchmark.

### C9 - Suite de regressao local

Status: concluido

Resultado:

- Testes, compile e checks direcionados passaram.

Impacto:

- Mantem estabilidade da primeira camada de robustez.

### C10 - Pendencias tecnicas iniciais finalizadas

Status: concluido

Resultado:

- `SQLInspector` com parser/fallback.
- Catalogo semantico versionado.
- Data profiling base.
- Taxonomia de erro semantico.
- Equivalencia SQL leve.
- Testes adversariais fora do benchmark.
- Telemetria semantica.
- Parsing melhor de resultados stringificados.

Impacto:

- Fecha a base tecnica para os proximos ciclos sem depender do ground truth atual.

## Medio Prazo - Status em andamento

Arquivo detalhado: `MEDIUM_LONG_TERM_CHECKPOINTS.md`

### M1 - Runner persistente de data profiling

Status: concluido

Objetivo:

Executar os specs de profiling contra o banco real e persistir resultados versionados.

Resultado:

- Runner CLI `src/semantic/profile_runner.py`.
- Loader/store tipado `src/semantic/profile_store.py`.
- Smoke real do runner gravado em `/tmp/txt2sql_semantic_profile_smoke.json`.

Impacto esperado:

- Melhor entendimento de cardinalidade, nulos, dominios de codigos e ranges temporais.

### M2 - Integracao do data profiling ao semantic planner

Status: concluido

Objetivo:

Usar perfis reais para enriquecer o plano com ambiguidades, ranges, nulos e dominios.

Resultado:

- `build_semantic_plan()` aceita `SemanticProfileStore` opcional.
- `plan_gate_node()` usa o perfil persistido quando disponivel.
- Hints de range temporal, cardinalidade, nulos e dominios entram em `ambiguities`.

Impacto esperado:

- Menos filtros errados, menos confusao de dominio e melhor interpretacao temporal.

### M3 - DSL semantica declarativa para metricas, dimensoes e joins

Status: concluido

Objetivo:

Evoluir o catalogo para declarar contratos completos de metricas, dimensoes, joins, granularidade e politicas de denominador.

Resultado:

- `src/semantic/catalog_schema.py` valida contratos do catalogo.
- `catalog.yml` declara `metric_type`, `default_scope`, `forbidden_filters`, `null_policy`, `aliases`, `grain` e `join_path`.
- Testes rejeitam metrica derivada incompleta e dimensao com join sem caminho.

Impacto esperado:

- Menos erro em joins, denominadores e fact/dimension grain.

### M4 - Geracao SQL guiada por semantic plan estruturado

Status: concluido

Objetivo:

Adicionar etapa estruturada de planner LLM e reconciliar com planner heuristico antes da SQL.

Resultado:

- `src/agent/semantic_planner.py` adiciona structured output para `SemanticPlan`.
- `src/semantic/plan_reconciler.py` preserva o plano heuristico como contrato de seguranca e registra conflitos do LLM.
- Workflow passa por `semantic_planner` antes de reasoning/SQL generation.

Impacto esperado:

- Melhor decomposicao e controle em hard queries multi-hop.

### M5 - Validador SQL baseado em AST/dialeto com contratos semanticos

Status: concluido

Objetivo:

Substituir a inspecao leve por AST real para validar tabelas, joins, filtros, agregacoes, janelas e CTEs.

Resultado:

- `src/semantic/sql_ast.py` extrai estrutura SQL via parser leve com fallback.
- `src/semantic/contract_validator.py` valida top-N por grupo, denominador de taxa, GROUP BY e join paths do catalogo.
- Validador semantico passa a usar a camada estrutural antes da execucao.

Impacto esperado:

- Menos falso positivo/negativo na validacao semantica.

### M6 - Repair semantico direcionado por causa raiz

Status: concluido

Objetivo:

Usar `SemanticErrorCategory` para orientar repair especifico.

Resultado:

- `src/semantic/repair_guidance.yml` mapeia categorias semanticas para instrucoes de reparo.
- `src/agent/semantic_repair.py` monta prompt de reparo com causa raiz e contrato violado.
- `repair_sql_node()` registra categoria original, guidance aplicado e validacao pos-reparo.

Impacto esperado:

- Mais recuperacao em falhas hard sem prompt generico.

### M7 - Avaliacao semantica independente de EX estrito

Status: pendente

Objetivo:

Criar avaliacao com plan accuracy, semantic validation pass rate, table/column coverage, repair success e taxonomia de erro.

Impacto esperado:

- Medir robustez real sem otimizar apenas EX.

### M8 - Suite metamorfica e adversarial expandida

Status: pendente

Objetivo:

Gerar variacoes equivalentes e nao equivalentes de perguntas para testar generalizacao.

Impacto esperado:

- Detectar fragilidade linguistica e colapso de escopo.

### M9 - Guardrails de anti-benchmark-hacking em CI

Status: pendente

Objetivo:

Automatizar deteccao de vazamento de benchmark em codigo runtime.

Impacto esperado:

- Evitar overfitting acidental em prompts, catalogo e validadores.

## Longo Prazo - Status pendente

Arquivo detalhado: `MEDIUM_LONG_TERM_CHECKPOINTS.md`

### L1 - Arquitetura neuro-simbolica com semantic layer como fonte de verdade

Status: pendente

Objetivo:

LLM interpreta linguagem; camada simbolica versionada resolve metricas, joins, regras e validacao critica.

Impacto esperado:

- Mais confiabilidade e auditabilidade em producao.

### L2 - Planejamento hierarquico para hard queries

Status: pendente

Objetivo:

Decompor hard queries em operadores semanticos verificaveis.

Impacto esperado:

- Melhor raciocinio multi-hop sem depender de chain-of-thought livre.

### L3 - Execucao verificada com contraste e checks de invariantes

Status: pendente

Objetivo:

Executar checks auxiliares para detectar denominador errado, perda por join e cardinalidade inesperada.

Impacto esperado:

- Menos respostas executadas mas semanticamente erradas.

### L4 - Feedback loop humano e curadoria de dominio

Status: pendente

Objetivo:

Converter falhas reais em regras gerais revisadas, catalogo e testes adversariais.

Impacto esperado:

- Evolucao governada do conhecimento de dominio.

### L5 - Avaliacao continua com holdout rotativo e dados sinteticos controlados

Status: pendente

Objetivo:

Medir generalizacao em perguntas novas e reduzir dependencia do benchmark atual.

Impacto esperado:

- Menos incentivo a perseguir apenas EX do conjunto conhecido.

### L6 - Observabilidade de producao e monitoramento de drift semantico

Status: pendente

Objetivo:

Monitorar drift de schema, dados, falhas e categorias semanticas emergentes.

Impacto esperado:

- Manter confiabilidade fora do ambiente de avaliacao.

## Ordem recomendada de execucao

1. M1 - Runner persistente de data profiling.
2. M2 - Integracao do profiling ao planner.
3. M3 - DSL semantica declarativa.
4. M7 - Avaliacao semantica independente de EX.
5. M8 - Suite metamorfica expandida.
6. M9 - Guardrails anti-benchmark-hacking em CI.
7. M5 - Validador AST/dialeto.
8. M6 - Repair semantico por causa raiz.
9. M4 - Planner estruturado LLM reconciliado.
10. L1-L6 conforme maturidade de catalogo, avaliacao e observabilidade.

## Diferenca entre generalizacao e ajuste artificial

Melhoria de generalizacao:

- Cria regra por classe semantica.
- Usa catalogo de dominio versionado.
- Adiciona teste adversarial fora do benchmark.
- Melhora comportamento em familias de perguntas.
- Mantem explicacao de causa raiz.

Ajuste artificial ao ground truth:

- Codifica pergunta literal.
- Usa IDs `GT###` no runtime.
- Usa valor esperado como regra.
- Ajusta prompt para caso unico.
- Mede sucesso apenas por EX no conjunto atual.

## Politica para novos checkpoints

Todo novo checkpoint deve declarar:

- objetivo tecnico
- status
- artefatos
- criterios de aceite
- testes
- impacto esperado em robustez
- risco de overfitting
- como evita benchmark hacking
