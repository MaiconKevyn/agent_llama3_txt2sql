# Checkpoints de Medio e Longo Prazo - Agente Text-to-SQL

Data de criacao: 2026-05-05

Objetivo: planejar as proximas evolucoes do agente para responder bem perguntas novas sobre a base, com foco em generalizacao, robustez semantica e confiabilidade do SQL. Estes checkpoints nao devem ser usados para tunar perguntas do ground truth atual nem para aumentar artificialmente `execution accuracy`.

## Principios

- Melhorar compreensao semantica da base antes de gerar SQL.
- Separar conhecimento de dominio reutilizavel de exemplos de benchmark.
- Validar a intencao da pergunta, nao apenas sintaxe SQL.
- Avaliar por classes de erro e comportamento em perguntas novas.
- Detectar regressao, benchmark hacking e dependencia excessiva do ground truth.
- Priorizar artefatos versionados, testaveis e auditaveis.

## Medio Prazo

### M1 - Runner persistente de data profiling

Status: concluido

Objetivo:

Executar os specs de profiling ja criados em `src/semantic/data_profile.py` contra o banco real e persistir os resultados para uso por planner, table selection, prompts, validadores e avaliacao.

Implementacao:

- [x] Criar runner CLI para data profiling.
- [x] Executar `default_profile_specs()` contra o banco configurado.
- [x] Persistir perfis em arquivo versionado, por exemplo `src/semantic/profiles/generated_profile.json`.
- [x] Incluir timestamp, fonte do banco, total de linhas por tabela e versao do catalogo semantico.
- [x] Calcular `row_count`, `null_count`, `distinct_count`, `min_value`, `max_value` e top valores.
- [x] Expor loader tipado para consumo pelo agente.

Artefatos:

- `src/semantic/profile_runner.py`
- `src/semantic/profiles/generated_profile.json`
- `tests/test_data_profile_runner.py`

Criterios de aceite:

- Perfis carregam sem acessar o banco durante inferencia normal.
- Colunas criticas possuem cardinalidade, nulos e exemplos de dominio.
- O runner pode ser reexecutado sem editar codigo.
- O arquivo gerado nao contem respostas de benchmark nem queries ground truth.

Testes:

- Unitario para parser/loader do perfil: `tests/test_data_profile_runner.py`.
- Smoke test do runner com executor mock e banco real via `/tmp/txt2sql_semantic_profile_smoke.json`.
- Teste de consistencia: perfil cobre specs centrais declaradas em `default_profile_specs()`.

Evidencias de implementacao:

- Criado `src/semantic/profile_runner.py`.
- Criado `src/semantic/profile_store.py`.
- Criado `src/semantic/profiles/README.md` para orientar geracao local de `generated_profile.json`.
- Smoke real executado com `python -m src.semantic.profile_runner --output /tmp/txt2sql_semantic_profile_smoke.json --max-specs 2`.
- O snapshot real foi mantido em `/tmp` para evitar versionar dados locais sem decisao explicita.

Impacto esperado:

- Reduz erro em dominios codificados, filtros temporais e interpretacao de granularidade.
- Melhora generalizacao porque o agente passa a entender distribuicoes reais da base, nao apenas exemplos.

Risco de overfitting:

- Baixo, se o perfil for derivado da base inteira e nao de perguntas do benchmark.

### M2 - Integracao do data profiling ao semantic planner

Status: concluido

Objetivo:

Usar os perfis para enriquecer o `SemanticPlan` com informacoes de dominio, ambiguidades e politicas de nulos.

Implementacao:

- [x] Incluir no plano sinais de cardinalidade de dimensoes.
- [x] Detectar se coluna e identificador, categoria, valor numerico ou temporal com base no perfil.
- [x] Adicionar `ambiguities` quando a pergunta usar termos com multiplas resolucoes possiveis.
- [x] Usar ranges temporais reais para evitar filtros fora da cobertura da base.
- [x] Usar nulos e top valores para decidir quando bucket "sem informacao" deve ser explicitado.

Artefatos:

- `src/semantic/profile_store.py`
- `src/semantic/planner.py`
- `tests/test_profile_aware_planner.py`

Criterios de aceite:

- Perguntas com termos ambiguos geram `ambiguities`.
- Perguntas temporais fora do range geram aviso no plano.
- O planner nao altera comportamento com base em IDs de benchmark.

Testes:

- Testes com perfis pequenos sinteticos: `tests/test_profile_aware_planner.py`.
- Casos adversariais com filtro temporal fora de cobertura e identificador de alta cardinalidade.
- Testes de regressao para nao quebrar top-N, taxa, ausencia e bucket desconhecido.

Evidencias de implementacao:

- `build_semantic_plan()` agora aceita `SemanticProfileStore` opcional.
- `plan_gate_node()` carrega `generated_profile.json` quando existir e degrada para plano sem perfil quando nao existir.
- O perfil adiciona hints em `ambiguities`, sem criar atalhos pergunta-resposta.

Impacto esperado:

- Reduz filtros errados, colunas erradas e interpretacao incorreta de dominios.

Risco de overfitting:

- Medio, se top valores forem usados como atalhos para perguntas especificas. Mitigacao: usar perfis apenas como contexto de dominio e validacao, nao como mapa pergunta-resposta.

### M3 - DSL semantica declarativa para metricas, dimensoes e joins

Status: concluido

Objetivo:

Evoluir `src/semantic/catalog.yml` para uma camada semantica declarativa com contratos completos de metricas, dimensoes, joins, filtros obrigatorios, granularidade e politicas de denominador.

Implementacao:

- [x] Definir schema Pydantic para validar o YAML do catalogo.
- [x] Adicionar `join_path`, `grain`, `default_scope`, `required_filters`, `forbidden_filters`, `null_policy`.
- [x] Separar metricas de evento, metricas de entidade e metricas derivadas.
- [x] Registrar dimensoes padrao de residencia versus localizacao do hospital.
- [x] Adicionar aliases linguisticas sem amarrar a perguntas do benchmark.

Artefatos:

- `src/semantic/catalog_schema.py`
- `src/semantic/catalog.yml`
- `tests/test_semantic_catalog_schema.py`

Criterios de aceite:

- Catalogo invalido falha em teste.
- Toda metrica derivada declara numerador, denominador e escopo.
- Toda dimensao com join declara caminho e grain esperado.

Testes:

- Schema validation do catalogo: `tests/test_semantic_catalog_schema.py`.
- Testes de metricas derivadas: taxa de mortalidade exige numerador, denominador e escopo.
- Testes de dimensoes conflitantes: residencia versus localizacao do hospital via `join_path`.

Evidencias de implementacao:

- Criado `src/semantic/catalog_schema.py`.
- `src/semantic/catalog.yml` declara metric type, default scope, filtros proibidos, null policy, aliases e join paths.
- Catalogo invalido falha em teste antes de chegar no runtime do agente.

Impacto esperado:

- Reduz erro de joins, denominadores e granularidade.
- Torna contexto reutilizavel e auditavel.

Risco de overfitting:

- Baixo se aliases forem gerais e revisados para evitar perguntas literais do benchmark.

### M4 - Geracao SQL guiada por semantic plan estruturado

Status: concluido

Objetivo:

Trocar a injecao textual simples do plano por um fluxo no qual o LLM deve primeiro preencher ou confirmar um `SemanticPlan` estruturado e so depois gerar SQL.

Implementacao:

- [x] Criar etapa `semantic_planner_llm` com structured output.
- [x] Comparar plano LLM com plano heuristico.
- [x] Rejeitar ou pedir reparo quando houver conflito de intent, metrica, dimensao ou granularidade.
- [x] Persistir diferencas entre plano heuristico e plano LLM.
- [x] Usar catalogo semantico para restringir metricas/dimensoes permitidas.

Artefatos:

- `src/agent/semantic_planner.py`
- `src/semantic/plan_reconciler.py`
- `tests/test_semantic_plan_reconciliation.py`

Criterios de aceite:

- SQL generation recebe plano reconciliado, nao apenas query textual.
- Conflitos de taxa, top-N por grupo e ausencia sao detectados antes da SQL.
- Planner nao usa exemplos de ground truth.

Testes:

- Mock LLM com plano conflitante: `tests/test_semantic_planner_node.py`.
- Casos adversariais para output shape: `tests/test_semantic_plan_reconciliation.py`.
- Casos de pergunta ambigua preservam `ambiguities` no plano reconciliado.

Evidencias de implementacao:

- Criado `src/agent/semantic_planner.py`.
- Criado `src/semantic/plan_reconciler.py`.
- Workflow agora executa `plan_gate -> semantic_planner -> query_planner/reasoning/generate_sql`.
- `semantic_planner` grava modo, confianca, conflitos, campos aceitos e campos rejeitados em `response_metadata`.
- Falha do LLM degrada para plano heuristico sem interromper o agente.

Impacto esperado:

- Melhora hard queries com multiplas condicoes e multiplos joins.

Risco de overfitting:

- Medio se prompts do planner incluirem exemplos do benchmark. Mitigacao: exemplos sinteticos e metamorfos, nao perguntas reais do conjunto avaliado.

### M5 - Validador SQL baseado em AST/dialeto com contratos semanticos

Status: concluido

Objetivo:

Evoluir o `SQLInspector` para uma validacao estrutural mais confiavel, reduzindo falsos positivos e falsos negativos de regex.

Implementacao:

- [x] Avaliar `sqlglot` ou parser equivalente para AST real.
- [x] Extrair tabelas, colunas, aliases, joins, filtros, agregacoes, janelas e CTEs.
- [x] Validar contrato de `SemanticPlan` contra AST.
- [x] Validar escopo de denominador e posicao de filtros.
- [x] Validar que joins respeitam caminhos declarados no catalogo.

Artefatos:

- `src/semantic/sql_ast.py`
- `src/semantic/contract_validator.py`
- `tests/test_sql_contract_validator.py`

Criterios de aceite:

- Aceita SQL equivalente com aliases diferentes.
- Rejeita filtros de desfecho no lugar errado.
- Rejeita joins fora do caminho semantico esperado.
- Rejeita top-N global quando pergunta pede por grupo.

Testes:

- SQLs equivalentes com CTE, subquery e aliases diferentes: `tests/test_sql_contract_validator.py`.
- SQLs invalidas semanticamente mas executaveis: filtro de desfecho em denominador, top-N global e join fora do catalogo.
- Fallback seguro se parser nao suportar uma sintaxe.

Evidencias de implementacao:

- Criado `src/semantic/sql_ast.py`.
- Criado `src/semantic/contract_validator.py`.
- `validate_sql_against_semantic_plan()` agora chama o contract validator estrutural.
- O projeto nao tinha `sqlglot`; foi usado parser leve com `sqlparse`/fallback regex para evitar nova dependencia de rede.

Impacto esperado:

- Aumenta confiabilidade da validacao antes da execucao.

Risco de overfitting:

- Baixo. A validacao e estrutural e baseada no contrato semantico.

### M6 - Repair semantico direcionado por causa raiz

Status: concluido

Objetivo:

Quando a SQL falhar na validacao semantica, gerar reparo com feedback especifico da taxonomia, em vez de pedir reparo generico.

Implementacao:

- [x] Mapear `SemanticErrorCategory` para instrucoes de reparo.
- [x] Incluir no prompt de repair o trecho do contrato violado.
- [x] Reexecutar validacao semantica apos repair.
- [x] Limitar ciclos para evitar loops.
- [x] Persistir causa original e causa apos repair.

Artefatos:

- `src/agent/semantic_repair.py`
- `src/semantic/repair_guidance.yml`
- `tests/test_semantic_repair_guidance.py`

Criterios de aceite:

- Erro de denominador gera instrucao de agregacao condicional.
- Erro de top-N por grupo gera instrucao de window partition.
- Erro de ausencia gera instrucao de anti-join ou aggregate-zero.

Testes:

- Mock de guidance para categorias centrais: `tests/test_semantic_repair_guidance.py`.
- Garantir que repair nao remove filtros de escopo corretos.

Evidencias de implementacao:

- Criado `src/agent/semantic_repair.py`.
- Criado `src/semantic/repair_guidance.yml`.
- `repair_sql_node()` usa guidance por causa raiz e inclui contrato violado no prompt.
- `validate_sql_node()` persiste validacao pos-reparo em `response_metadata.repair_attempts`.
- Reparos deterministas continuam restritos a padroes seguros, como remocao de filtro de metrica nao solicitado.

Impacto esperado:

- Aumenta taxa de recuperacao em hard queries sem mudar ground truth.

Risco de overfitting:

- Baixo se as instrucoes forem por categoria semantica, nao por pergunta.

### M7 - Avaliacao semantica independente de EX estrito

Status: pendente

Objetivo:

Criar avaliacao que mede qualidade semantica do agente alem de execution accuracy.

Implementacao:

- [ ] Registrar `semantic_plan`, SQL, resultado, taxonomia de falha e assinatura semantica.
- [ ] Adicionar metricas: plan accuracy, table/column coverage, semantic validation pass rate, repair success rate, error taxonomy distribution.
- [ ] Comparar SQL por assinatura semantica quando EX for estrito demais.
- [ ] Separar resultados por dificuldade e por categoria semantica.
- [ ] Criar dashboard/report markdown por rodada.

Artefatos:

- `evaluation/semantic/`
- `evaluation/semantic/run_semantic_eval.py`
- `evaluation/semantic/results/`
- `tests/test_semantic_eval_metrics.py`

Criterios de aceite:

- Report separa sintaxe, execucao, semantica e resposta final.
- EX nao e a unica metrica de sucesso.
- Falhas hard aparecem por taxonomia.

Testes:

- Fixtures pequenas com SQLs semanticamente equivalentes.
- Testes de agregacao de metricas.

Impacto esperado:

- Melhora tomada de decisao sem perseguir apenas o ground truth.

Risco de overfitting:

- Medio se a suite reutilizar apenas o benchmark atual. Mitigacao: incluir perguntas sinteticas, metamorfismo e holdout rotativo.

### M8 - Suite metamorfica e adversarial expandida

Status: pendente

Objetivo:

Avaliar generalizacao criando variacoes de perguntas que preservam a intencao mas mudam forma linguistica, ordem de filtros, sinonimos e granularidade explicita.

Implementacao:

- [ ] Criar gerador de pares metamorfos.
- [ ] Criar casos negativos que devem falhar semanticamente.
- [ ] Adicionar variacoes de idioma, plural, abreviacoes e sinonimos.
- [ ] Validar que perguntas equivalentes geram assinatura SQL compativel.
- [ ] Validar que perguntas diferentes nao colapsam para o mesmo plano.

Artefatos:

- `evaluation/semantic/metamorphic_cases.yml`
- `evaluation/semantic/run_metamorphic_eval.py`
- `tests/test_metamorphic_eval.py`

Criterios de aceite:

- Variacoes de uma pergunta produzem planos compativeis.
- Perguntas com mudanca real de escopo produzem planos diferentes.
- Nao usa perguntas literais do benchmark como fonte principal.

Testes:

- Pairs equivalentes: "por sexo", "para cada sexo", "em cada sexo".
- Pairs nao equivalentes: residencia do paciente versus localizacao do hospital.
- Pairs de denominador: taxa versus total de obitos.

Impacto esperado:

- Mede robustez real para perguntas novas.

Risco de overfitting:

- Baixo se os casos forem gerados por principios semanticos.

### M9 - Guardrails de anti-benchmark-hacking em CI

Status: pendente

Objetivo:

Automatizar deteccao de regras ou artefatos que possam indicar ajuste artificial ao benchmark.

Implementacao:

- [ ] Criar scanner para IDs de ground truth, perguntas literais e valores esperados em codigo runtime.
- [ ] Separar fixtures/evaluation assets de runtime code.
- [ ] Bloquear PR se runtime contiver referencias proibidas.
- [ ] Permitir referencias apenas em `evaluation/` e testes explicitamente marcados.
- [ ] Reportar diffs suspeitos em prompts, catalogo e validadores.

Artefatos:

- `scripts/check_benchmark_leakage.py`
- `.github/workflows/ci.yml`
- `tests/test_benchmark_leakage_guard.py`

Criterios de aceite:

- CI falha se `src/` contiver `GT###`, pergunta literal do benchmark ou valor esperado conhecido.
- CI permite arquivos de avaliacao declarados.
- Report explica caminho e padrao detectado.

Testes:

- Fixture com vazamento proposital.
- Fixture permitido em evaluation.

Impacto esperado:

- Reduz risco de benchmark hacking acidental.

Risco de overfitting:

- Baixo; e uma barreira contra overfitting.

## Longo Prazo

### L1 - Arquitetura neuro-simbolica com semantic layer como fonte de verdade

Status: pendente

Objetivo:

Transformar o agente em um sistema no qual o LLM interpreta a pergunta, mas metricas, joins, regras e validacoes criticas sao resolvidas por uma camada simbolica versionada.

Implementacao:

- [ ] Tornar catalogo semantico a fonte primaria de metricas e dimensoes.
- [ ] Gerar SQL a partir de plano + macros sempre que possivel.
- [ ] Usar LLM para preencher lacunas e resolver linguagem natural, nao para inventar regras.
- [ ] Criar fallback controlado para perguntas fora do catalogo.
- [ ] Versionar catalogo, perfis e prompts em conjunto.

Artefatos:

- `src/semantic/compiler.py`
- `src/semantic/macros/`
- `src/agent/neuro_symbolic_workflow.py`

Criterios de aceite:

- Queries de metricas catalogadas podem ser compiladas sem LLM para partes criticas.
- Mudancas de regra de negocio acontecem no catalogo, nao em prompts soltos.
- O agente reporta quando a pergunta esta fora da cobertura semantica.

Impacto esperado:

- Aumenta confiabilidade e auditabilidade em producao.

Risco de overfitting:

- Baixo se catalogo for baseado no dominio e revisado por principios, nao por benchmark.

### L2 - Planejamento hierarquico para hard queries

Status: pendente

Objetivo:

Resolver hard queries por decomposicao semantica controlada: intencao, entidades, metricas, filtros, agregacoes, ranking, validacao e resposta.

Implementacao:

- [ ] Criar planner hierarquico com etapas verificaveis.
- [ ] Separar entity resolution de metric resolution.
- [ ] Separar filtros de escopo de filtros de outcome.
- [ ] Criar verificadores para cada subplano.
- [ ] Permitir multi-step apenas quando a semantica exigir.

Artefatos:

- `src/agent/hierarchical_planner.py`
- `src/semantic/subplan_schema.py`
- `tests/test_hierarchical_planner.py`

Criterios de aceite:

- Queries com comparacao temporal geram subplanos por periodo.
- Queries top-N por grupo geram subplano de agregacao + ranking.
- Queries de taxa geram subplano de numerador e denominador.

Impacto esperado:

- Melhora raciocinio multi-hop sem depender de chain-of-thought livre.

Risco de overfitting:

- Medio se subplanos forem ajustados aos casos atuais. Mitigacao: desenhar subplanos por operadores semanticos universais.

### L3 - Execucao verificada com contraste e checks de invariantes

Status: pendente

Objetivo:

Antes de entregar resposta, executar checks auxiliares para detectar resultados improvaveis, denominadores errados, cardinalidade inesperada ou perda de linhas por join.

Implementacao:

- [ ] Criar invariantes por metrica e dimensao.
- [ ] Comparar denominador com query auxiliar quando houver taxa.
- [ ] Verificar perda de linhas em joins lookup.
- [ ] Verificar cardinalidade esperada do output shape.
- [ ] Alertar ou reparar quando invariantes falharem.

Artefatos:

- `src/semantic/invariants.py`
- `src/agent/semantic_verifier.py`
- `tests/test_semantic_invariants.py`

Criterios de aceite:

- Taxa de mortalidade nao pode ter denominador igual ao total de obitos por construcao.
- LEFT JOIN necessario para bucket desconhecido e verificado.
- Top-N por grupo retorna ate N por grupo.

Impacto esperado:

- Reduz respostas executadas mas semanticamente erradas.

Risco de overfitting:

- Baixo se invariantes forem matematicos e estruturais.

### L4 - Feedback loop humano e curadoria de dominio

Status: pendente

Objetivo:

Permitir que especialistas revisem falhas por taxonomia e promovam conhecimento de dominio para o catalogo sem transformar exemplos em regras ad hoc.

Implementacao:

- [ ] Criar formato de review de erro semantico.
- [ ] Diferenciar bug de dominio, bug de planner, bug de validator e lacuna de contexto.
- [ ] Criar processo de promocao: falha -> regra geral -> teste adversarial -> catalogo.
- [ ] Rejeitar mudancas que so resolvem pergunta especifica.

Artefatos:

- `evaluation/semantic/review_template.md`
- `semantic_change_policy.md`
- `tests/test_semantic_change_policy.py`

Criterios de aceite:

- Toda nova regra deve ter justificativa geral.
- Toda regra nova deve ter teste adversarial fora do benchmark.
- Reviews registram categoria de erro e impacto esperado.

Impacto esperado:

- Melhora qualidade do dominio de forma governada.

Risco de overfitting:

- Baixo se o processo bloquear regras especificas.

### L5 - Avaliacao continua com holdout rotativo e dados sinteticos controlados

Status: pendente

Objetivo:

Criar um regime de avaliacao que mede generalizacao em perguntas novas, nao memorizacao do conjunto atual.

Implementacao:

- [ ] Separar benchmark atual, holdout privado e suite sintetica.
- [ ] Rotacionar subconjuntos de avaliacao.
- [ ] Reportar metricas por familia semantica.
- [ ] Medir estabilidade entre runs.
- [ ] Detectar ganhos localizados demais em um conjunto especifico.

Artefatos:

- `evaluation/semantic/holdout_protocol.md`
- `evaluation/semantic/synthetic_generator.py`
- `evaluation/semantic/reporting.py`

Criterios de aceite:

- Toda melhoria precisa mostrar efeito em mais de uma familia semantica ou justificar escopo.
- Report sinaliza ganho suspeito concentrado em perguntas conhecidas.
- Holdout nao entra em prompts nem validadores.

Impacto esperado:

- Reduz incentivo a otimizar apenas EX do benchmark atual.

Risco de overfitting:

- Baixo se holdout for protegido e rotativo.

### L6 - Observabilidade de producao e monitoramento de drift semantico

Status: pendente

Objetivo:

Monitorar o agente em uso real para identificar novas ambiguidades, mudancas no banco, drift de dominio e categorias de falha emergentes.

Implementacao:

- [ ] Logar plano, SQL, validacoes, repair, resultado e feedback de usuario.
- [ ] Agregar falhas por taxonomia.
- [ ] Detectar mudancas de schema e perfil de dados.
- [ ] Alertar quando uma metrica ou dimensao passar a falhar mais.
- [ ] Criar relatorio periodico de robustez semantica.

Artefatos:

- `src/observability/semantic_events.py`
- `evaluation/semantic/drift_report.py`
- dashboards de MLflow/LangSmith ou equivalente

Criterios de aceite:

- Toda execucao tem trace semantico auditavel.
- Drift de schema/perfil e identificado antes de afetar muitas respostas.
- Falhas novas viram candidatos a testes adversariais.

Impacto esperado:

- Mantem confiabilidade fora do ambiente de avaliacao.

Risco de overfitting:

- Baixo. Dados de producao devem alimentar diagnostico e curadoria, nao regras diretas.
