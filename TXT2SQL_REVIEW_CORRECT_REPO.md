# Revisão técnica do repositório `txt2sql_refactor_openai_v2`

## 1. Objetivo desta revisão

Este documento revisa o repositório correto:

`/home/maiconkevyn/PycharmProjects/txt2sql_refactor_openai_v2`

Objetivos:
- analisar a arquitetura atual do agente Text-to-SQL;
- avaliar acurácia, robustez, segurança, organização e debugabilidade;
- cruzar o estado atual do projeto com boas práticas modernas de Text-to-SQL usando LangChain e LangGraph;
- propor um plano detalhado e priorizado de melhoria;
- não alterar código do projeto.

Observação importante: este documento foi produzido a partir da leitura do código e dos documentos do próprio repositório, além de alinhamento com boas práticas atuais para agentes Text-to-SQL operados com LLMs, LangGraph, FastAPI e avaliação contínua.

---

## 2. Resumo executivo

Minha conclusão é que este repositório está em um estágio interessante de maturidade técnica: ele já tem uma arquitetura agentic explícita, avaliação, baseline, API, CLI, frontend, guardrails de segurança SQL, rastreamento de erros no estado e sinais claros de preocupação com experimentação.

Ao mesmo tempo, os principais gargalos para torná-lo realmente "product-ready" não parecem estar no conceito central do agente, e sim em cinco frentes:

1. consistência entre documentação, benchmark, código e dependências;
2. reprodutibilidade do ambiente e confiabilidade da suíte de testes;
3. governança do pipeline de avaliação e versionamento de prompts/datasets;
4. endurecimento operacional da API e da execução SQL em produção;
5. observabilidade por estágio para explicar por que o agente acertou ou errou.

Em termos práticos:
- o desenho do pipeline é bom;
- o projeto já tem instrumentação conceitual suficiente para virar um sistema auditável;
- mas ainda há drift entre artefatos, fragilidade no setup local e lacunas de hardening que impedem tratá-lo como um produto robusto.

---

## 3. O que foi inspecionado

Arquivos e áreas principais analisadas:
- `README.md`
- `pyproject.toml`
- `requirements.txt`
- `ARCH.md`
- `ROADMAP.md`
- `evaluation/README.md`
- `src/agent/workflow.py`
- `src/agent/orchestrator.py`
- `src/agent/validation.py`
- `src/agent/state_helpers.py`
- `src/application/config/simple_config.py`
- `src/interfaces/api/main.py`
- `src/memory/vector_store.py`
- `frontend/server.js`
- `.gitignore`
- testes em `tests/`

Também foi feita validação operacional básica:
- confirmação de que este é um repositório Git válido;
- inspeção de branch e estado do working tree;
- tentativa de rodar `pytest -q`;
- comparação do projeto com boas práticas atuais de Text-to-SQL com LangChain/LangGraph.

---

## 4. Estado factual atual do repositório

### 4.1 Git

Estado observado:
- repositório Git válido;
- branch atual: `agent_v3`;
- working tree limpo no momento da revisão.

### 4.2 Estrutura funcional

O projeto contém, de forma clara:
- núcleo do agente em `src/agent/`;
- configuração e metadados de domínio em `src/application/config/`;
- interfaces em `src/interfaces/api` e `src/interfaces/cli`;
- camada de banco em `src/infrastructure/database/`;
- baseline separado em `baselines/rich_prompt_baseline/`;
- avaliação em `evaluation/`;
- frontend web em `frontend/`.

### 4.3 Stack inferida

Pelo `README.md`, `pyproject.toml` e `requirements.txt`, a stack principal é:
- Python 3.11+
- LangChain
- LangGraph
- OpenAI
- FastAPI
- SQLAlchemy / psycopg2
- SQLite checkpointing para memória de sessão
- MLflow opcional
- Sentence Transformers para seleção semântica de tabelas
- frontend Node/Express

---

## 5. Pontos fortes do projeto

### 5.1 Pipeline explícito e modular

O fluxo em `src/agent/workflow.py` é um dos maiores ativos do projeto. O pipeline está organizado em etapas semanticamente separadas:
- classificação;
- listagem/seleção de tabelas;
- enriquecimento de schema;
- plan gate;
- planner;
- reasoning;
- geração de SQL;
- self-consistency opcional;
- validação;
- repair;
- execução;
- síntese de resposta.

Isso é muito melhor do que um agente monolítico de "pergunta -> SQL -> resposta", porque facilita:
- depuração por estágio;
- ablation por componente;
- medição de ganho incremental;
- introdução de políticas específicas de segurança e qualidade.

### 5.2 Estado estruturado com sinais de auditabilidade

`src/agent/state_helpers.py` e `state_models.py` mostram que o projeto já evoluiu para algo mais auditável. Há campos como:
- `failure_taxonomy`
- `single_fallback_active`
- `single_fallback_reason`
- `phase_timings`
- `execution_time_total`
- `validation_retry_count`
- `execution_retry_count`
- `ablation_flags`

Isso é excelente base para construir observabilidade real de acurácia.

### 5.3 Validação semântica local

`src/agent/validation.py` contém regras semânticas de alto valor prático, por exemplo:
- uso incorreto de `socioeconomico` sem filtro de métrica;
- join indevido com `tempo` que pode gerar explosão cartesiana;
- uso espúrio de `VAL_UTI`;
- pergunta de contagem sem `COUNT(*)`;
- `NOT IN` inseguro com subquery;
- top-N por grupo sem `PARTITION BY`;
- filtro `MORTE = false` quando a pergunta não pede isso.

Esse tipo de regra gera muito ROI em Text-to-SQL. Em vez de depender apenas do LLM, o projeto já usa conhecimento determinístico do domínio.

### 5.4 Presença de baseline e avaliação

A existência de:
- `baselines/rich_prompt_baseline/`
- `evaluation/metrics/`
- `evaluation/runners/`
- `run_ablation.py`
- `run_regression.py`

indica uma mentalidade correta de AI Engineering: comparar arquiteturas, medir regressão e não confiar apenas em impressão subjetiva.

### 5.5 Preocupação com segurança na interface web

`frontend/server.js` já traz:
- `helmet`
- `compression`
- CORS configurável
- `express-rate-limit`
- limites de tamanho de payload
- validação básica da pergunta

Isso mostra que o projeto já considera aspectos de exposição real, não apenas protótipo acadêmico.

---

## 6. Principais problemas encontrados

## 6.1 Drift de documentação e narrativa técnica

Este é provavelmente o problema sistêmico mais importante no momento.

Há sinais claros de múltiplas versões narrativas do projeto coexistindo:

### Conflitos observados

1. `README.md`
- descreve stack atual com OpenAI, LangGraph, FastAPI, PostgreSQL/DuckDB;
- menciona benchmark mais moderno, pipeline modular e pyproject/uv.

2. `evaluation/README.md`
- ainda fala em LLaMA 3.1:8b via Ollama;
- fala em dataset de 59 queries;
- descreve resultados e arquitetura de uma fase anterior do projeto.

3. `ARCH.md`
- contém uma revisão crítica profunda e útil;
- sugere um snapshot analítico mais novo do que `evaluation/README.md`;
- discute 120 queries e comparação entre baseline e agente.

4. `ROADMAP.md`
- traz uma linha de evolução parcialmente já executada, parcialmente pendente;
- em alguns pontos descreve um estado que já parece ter mudado no código.

### Impacto

Esse drift causa:
- dificuldade para onboard de novos colaboradores;
- risco de conclusões erradas sobre métricas reais;
- problemas para reproduzir paper, benchmark e setup de produção;
- menor confiabilidade do projeto como ativo de portfólio e como base para produto.

### Conclusão

Hoje o projeto parece tecnicamente mais maduro do que a sua documentação consolidada.

---

## 6.2 Fragilidade de reprodutibilidade e setup local

A execução de `pytest -q` falhou na coleta, com erros concretos como:
- `ModuleNotFoundError: No module named 'psycopg2'`
- `ModuleNotFoundError: No module named 'langchain_openai'`
- erros de import em módulos como `src.agent.cli_session`, `src.utils.logging_setup`, `src.agent.metrics`, `src.agent.orchestrator_support`

Observações importantes:
- os arquivos existem no repositório;
- um teste manual de import de `src.agent.cli_session` funcionou no shell Python dentro do repo;
- isso sugere que o problema maior não é ausência de arquivo, mas inconsistência de ambiente/instalação/coleta de testes.

### Diagnóstico provável

Os testes hoje parecem depender de pelo menos três coisas que não estão garantidas de forma robusta:
- ambiente Python corretamente provisionado com dependências instaladas;
- resolução estável de import path no contexto do pytest;
- separação limpa entre testes unitários puros e testes que exigem integrações opcionais.

### Impacto

Isso é crítico porque sem suíte reproduzível:
- não existe confiança forte para refactor;
- não existe baseline seguro para regressão;
- a documentação de arquitetura perde valor operacional.

---

## 6.3 Dependências inconsistentes com o código

`src/memory/vector_store.py` usa:
- `chromadb`
- `chromadb.utils.embedding_functions`

Mas `pyproject.toml` e `requirements.txt` inspecionados destacam `sentence-transformers`, sem evidência explícita de `chromadb` nas dependências canônicas lidas nesta revisão.

Isso sugere uma das opções abaixo:
- o módulo está órfão / não integrado de fato;
- a dependência ficou faltando;
- a funcionalidade está em estado experimental e sem governança clara.

### Impacto

Esse tipo de discrepância é perigoso porque produz:
- código aparentemente disponível, mas não executável em ambiente limpo;
- falsa sensação de cobertura funcional;
- dificuldade de distinguir o que é parte do produto e o que é experimento residual.

---

## 6.4 Exposição excessiva na API backend

Em `src/interfaces/api/main.py`, a API está simples e funcional, mas ainda permissiva demais para produção:
- `CORSMiddleware` com `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`;
- tratamento de erro retorna texto de exceção diretamente ao cliente;
- não há camada explícita de autenticação/autorização;
- não há controle de quota por usuário ou tenant;
- não há limitação operacional por endpoint além do que existe no frontend proxy.

### Impacto

Se a FastAPI for exposta diretamente:
- risco de uso indevido;
- maior superfície de abuso de custo do LLM;
- risco de vazamento de detalhes internos de erro;
- dificuldade de isolamento entre ambiente interno e público.

---

## 6.5 Segurança SQL presente, mas ainda não plenamente endurecida como política de execução

O projeto já tem bons sinais de segurança:
- bloqueio para não-`SELECT` no fluxo geral;
- validação semântica local;
- camadas de validação e repair;
- consciência de joins perigosos e padrões ruins.

Mas, para uso em produção, ainda faltam políticas mais fortes e verificáveis, como:
- validação estrutural via AST SQL;
- orçamento explícito de custo/tempo por query;
- `EXPLAIN`/dry-run como contrato operacional mais visível;
- denylist/allowlist de funções SQL sensíveis;
- limitação mais rígida de cardinalidade e payload de resposta;
- política padronizada para queries ambíguas em vez de sempre prosseguir.

---

## 6.6 Governança de documentos estratégicos está ruim

O `.gitignore` atualmente ignora:
- `CLAUDE.md`
- `ARCH.md`
- `ROADMAP.md`
- `ABLATION_PLAN.md`
- `docs/CBMS/`

Isso é um problema porque vários desses arquivos são, na prática, documentação estratégica do produto e da pesquisa.

### Impacto

Quando documentos de arquitetura e roadmap ficam fora da governança principal do repositório:
- decisões de engenharia perdem rastreabilidade;
- colaboradores não compartilham o mesmo contexto;
- análise de evolução do sistema fica fragmentada;
- o projeto fica menos confiável como base de produto e publicação.

Observação: não alterei isso; apenas registro como finding.

---

## 6.7 Sinais de experimento e produto ainda misturados

Há uma convivência de várias camadas no mesmo repo:
- agente produtivo;
- baseline de paper;
- runners de avaliação;
- frontend web;
- documentação de arquitetura;
- componentes experimentais como vector store;
- memória de sessão e MLflow.

Isso não é errado por si só, mas hoje o boundary entre:
- código de produto,
- código de avaliação,
- código experimental,
- documentação de pesquisa

não parece suficientemente explícito.

### Impacto

Isso afeta diretamente:
- organização do repo;
- onboarding;
- clareza de ownership;
- facilidade de refactor;
- readiness para deploy controlado.

---

## 7. Análise específica de acurácia

## 7.1 O projeto está apontando na direção certa

Pelas leituras feitas, os maiores drivers de acurácia aqui não são “mais passos agentic por si só”, e sim:
- schema linking;
- table selection;
- regras de domínio;
- validação semântica;
- repair com contexto de erro;
- possibilidade de ablation.

Isso está alinhado com o que hoje funciona melhor em Text-to-SQL sério.

## 7.2 O que parece faltar para evoluir a acurácia de forma explicável

As melhorias de maior valor para acurácia não parecem ser simplesmente trocar modelo. Elas parecem ser:

1. medir erro por estágio;
2. registrar explicitamente tabelas candidatas e tabela final escolhida;
3. registrar assumptions e ambiguidades por query;
4. separar falhas de:
   - classificação,
   - seleção de tabela,
   - schema linking,
   - geração SQL,
   - validação,
   - execução,
   - síntese final.

Sem isso, o projeto pode até melhorar EX, mas continuará com pouca explicabilidade causal.

## 7.3 Oportunidade clara: policy de clarification

Boas práticas atuais para Text-to-SQL em produção mostram que uma resposta melhor muitas vezes é:
- pedir esclarecimento,
- ou devolver a hipótese assumida de forma explícita,

e não necessariamente gerar SQL imediatamente.

No domínio DATASUS isso é especialmente importante para ambiguidades como:
- município de residência vs de ocorrência;
- internações vs óbitos vs casos;
- janela temporal implícita;
- indicador absoluto vs taxa;
- nível geográfico da agregação.

Se a policy de clarification ficar mais central no produto, a acurácia percebida e a segurança semântica tendem a subir.

---

## 8. Análise de organização do repositório

## 8.1 Estrutura geral é boa

A macro-organização do repo é boa e profissional:
- `src/`
- `tests/`
- `evaluation/`
- `baselines/`
- `frontend/`
- `docs/`

## 8.2 O problema não é a árvore; é a governança

O principal problema não é “falta de pasta certa”, e sim:
- coexistência de artefatos de gerações diferentes;
- documentos estratégicos fora da governança principal;
- código experimental e operacional pouco separados por status;
- dependências e docs com drift.

## 8.3 Recomendação de organização

Sugestão estrutural de status:
- `src/` = produto suportado;
- `evaluation/` = benchmark e regressão suportados;
- `baselines/` = comparação experimental suportada;
- `experiments/` = tudo que não faz parte do caminho principal;
- `docs/adrs/` = decisões de arquitetura versionadas;
- `docs/benchmarks/` = benchmark, versões, resultados canônicos e metodologia;
- `docs/operations/` = deploy, observabilidade, incidentes, runbooks.

---

## 9. Análise de robustez e operação

## 9.1 O projeto já pensa em robustez

Há vários sinais bons:
- retries no workflow;
- contador de ciclos;
- phase timings;
- métricas coletadas pelo orquestrador;
- health report;
- logs estruturados;
- frontend com rate limit;
- MLflow opcional.

## 9.2 O que ainda falta para robustez “de produto”

Para virar produto com segurança operacional, ainda faltam ao menos:
- suíte de testes passando em ambiente limpo;
- CI com smoke tests, lint e regressão de benchmark;
- timeouts e budgets padronizados por etapa;
- rastreabilidade de versão de prompt, benchmark, modelo e schema;
- replay fácil de runs com falha;
- política clara de fallback quando confiança é baixa;
- separação entre logs de desenvolvimento e logs de auditoria.

---

## 10. Análise de segurança e readiness para produção

## 10.1 Posição atual

O projeto está acima da média de protótipos acadêmicos, mas ainda abaixo do nível recomendado para exposição ampla em produção.

## 10.2 Riscos principais

1. API backend permissiva demais se exposta diretamente;
2. falta de auth/authz explícitos;
3. erros retornando detalhes internos;
4. queries LLM-driven sem camada AST/policy mais forte;
5. ambiente e testes não reproduzíveis o suficiente;
6. ausência de contrato operacional claro para bloquear ambiguidades críticas.

## 10.3 Avaliação honesta

Se fosse necessário classificar a prontidão atual:
- excelente como base de pesquisa aplicada;
- boa como demo técnica séria;
- promissora como produto interno assistido;
- ainda não pronta para exposição pública mais ampla sem mais hardening.

---

## 11. Alinhamento com boas práticas modernas de Text-to-SQL com LangChain/LangGraph

Com base no alinhamento externo feito durante esta revisão, as melhores práticas mais relevantes para este projeto são:

1. separar planejamento de geração de SQL;
2. usar schema linking guiado por catálogo semântico e retrieval;
3. preferir camada semântica / views certificadas em vez de acesso livre a tabelas brutas;
4. validar SQL estruturalmente antes de executar;
5. usar loop de repair com orçamento explícito;
6. exigir saída estruturada do LLM com assumptions e contexto;
7. pedir clarification quando a ambiguidade for material;
8. avaliar com EX/CM/EM e taxonomia de erro;
9. montar benchmark orientado a casos reais do domínio;
10. registrar tracing por nó do LangGraph;
11. versionar prompts, regras, datasets e resultados;
12. usar few-shot dinâmico por tipo de consulta;
13. ter guardrails operacionais na API e no executor SQL.

O ponto importante aqui é que o projeto já está razoavelmente alinhado com vários desses princípios. O gap não é conceitual; é principalmente de consolidação, governança e operacionalização.

---

## 12. Plano detalhado de melhoria

## Fase 1 — Higiene crítica e confiabilidade básica

Prioridade máxima.

### Objetivos
- eliminar drift de documentação;
- tornar o ambiente reproduzível;
- restabelecer confiança na suíte de testes.

### Ações
1. Consolidar um "source of truth" para:
   - modelo padrão;
   - benchmark oficial atual;
   - número de queries oficial;
   - stack oficial;
   - fluxo oficial do agente.
2. Atualizar `evaluation/README.md` para o estado atual ou separar explicitamente como histórico.
3. Revisar `ARCH.md` e `ROADMAP.md` para marcar o que já foi feito, o que está obsoleto e o que permanece válido.
4. Corrigir o setup para que `pytest -q` rode em ambiente limpo via `uv sync --extra dev`.
5. Garantir que testes unitários puros não dependam de integrações opcionais ausentes.
6. Tornar explícita a política de dependências opcionais, especialmente para MLflow, ChromaDB e recursos experimentais.

### Critério de pronto
- documentação coerente;
- setup reprodutível;
- testes coletando e rodando com sucesso ou claramente segmentados por marker.

---

## Fase 2 — Observabilidade e debug de acurácia

### Objetivos
- explicar erros;
- permitir replay e auditoria;
- medir contribuição de cada estágio.

### Ações
1. Persistir por query:
   - pergunta original;
   - rota escolhida;
   - tabelas candidatas;
   - tabela final;
   - schema enviado ao modelo;
   - SQL gerado;
   - SQL reparado;
   - resultado de validação;
   - taxonomia de falha;
   - tempo por estágio;
   - modelo, prompt_version, git_sha, benchmark_version.
2. Padronizar eventos por nó do LangGraph em formato estruturado.
3. Criar um report por execução com breakdown por estágio.
4. Adicionar dashboard simples de erro por categoria:
   - table selection;
   - schema mismatch;
   - semantic validation;
   - execution failure;
   - ambiguity/clarification.
5. Tornar replay de queries falhas um fluxo oficial de debug.

### Critério de pronto
- toda falha relevante consegue ser localizada em um estágio específico do pipeline.

---

## Fase 3 — Hardening de segurança e execução

### Objetivos
- reduzir risco operacional;
- endurecer comportamento em produção.

### Ações
1. Introduzir validação AST para SQL além das regex e regras semânticas atuais.
2. Formalizar allowlist/denylist de operações, funções e padrões SQL.
3. Adicionar orçamento de execução:
   - timeout;
   - row limit;
   - limite de tamanho de resposta;
   - limite de tentativas de repair;
   - limite de custo/token por query.
4. Fazer `EXPLAIN`/dry-run parte explícita do contrato de execução quando aplicável.
5. Endurecer FastAPI:
   - CORS restrito por ambiente;
   - mensagens de erro sanitizadas;
   - autenticação/autorização;
   - rate limit também no backend principal;
   - request IDs e audit trail.
6. Definir política para queries ambíguas: esclarecer antes de executar quando houver risco semântico alto.

### Critério de pronto
- backend exposto com superfície menor de abuso e maior auditabilidade.

---

## Fase 4 — Ganhos de acurácia de alto ROI

### Objetivos
- melhorar qualidade sem aumentar complexidade de forma cega.

### Ações
1. Fortalecer table selection com logging comparável entre:
   - heurística;
   - embeddings;
   - escolha final do LLM.
2. Criar confidence score operacional e usar isso em fallback/clarification.
3. Tornar assumptions explícitas na geração de SQL.
4. Expandir benchmark de ambiguidades reais do domínio DATASUS.
5. Fazer ablation contínua de componentes:
   - sem reasoning;
   - sem self-consistency;
   - sem validation;
   - sem repair;
   - sem schema enrichment.
6. Priorizar melhoria do catálogo semântico de schema e views analíticas confiáveis.

### Critério de pronto
- melhoria de EX acompanhada de explicação causal e menor taxa de erro semântico silencioso.

---

## Fase 5 — Organização e governança de produto

### Objetivos
- facilitar manutenção e colaboração.

### Ações
1. Separar claramente código suportado de código experimental.
2. Mover ou marcar componentes experimentais como `experimental`/`deprecated` quando aplicável.
3. Versionar ADRs em `docs/adrs/`.
4. Decidir o status oficial de:
   - `ARCH.md`
   - `ROADMAP.md`
   - `ABLATION_PLAN.md`
   - `vector_store.py`
5. Revisar `.gitignore` para não excluir documentação estratégica que deveria ser compartilhada.
6. Definir convenção de versionamento para prompts, benchmarks e artefatos de avaliação.

### Critério de pronto
- qualquer colaborador entende rapidamente o que é core, o que é experimento e o que é histórico.

---

## 13. Top 12 ações prioritárias

Se fosse preciso escolher apenas as ações de maior ROI agora, eu faria nesta ordem:

1. Fazer o ambiente oficial instalar e rodar `pytest` de forma reproduzível.
2. Corrigir e consolidar a documentação oficial do benchmark atual.
3. Padronizar versionamento de `prompt_version`, `git_sha`, `model_id`, `benchmark_version` em toda avaliação.
4. Persistir tracing por nó do LangGraph.
5. Medir e expor taxonomia de erro por query.
6. Endurecer a FastAPI com CORS restrito, erro sanitizado e auth.
7. Introduzir validação AST/policy para SQL.
8. Tornar clarification uma policy explícita para ambiguidades críticas.
9. Auditar e formalizar o papel da seleção de tabelas como principal gargalo de acurácia.
10. Resolver drift de dependências opcionais como `chromadb`.
11. Revisar `.gitignore` para documentos de arquitetura/roadmap.
12. Separar claramente produto, benchmark e experimento dentro do repo.

---

## 14. Julgamento final

O repositório correto, `txt2sql_refactor_openai_v2`, é uma base boa e tecnicamente séria para um agente Text-to-SQL de domínio especializado.

Minha avaliação final é:

### Em acurácia
Bom potencial, especialmente porque já usa validação semântica e pipeline modular. O próximo salto depende mais de observabilidade do erro e governança do schema/prompt do que de “mais agentic complexity”.

### Em organização
A estrutura base é boa, mas o projeto sofre com drift documental e mistura de artefatos de pesquisa, produto e experimento.

### Em robustez
Acima da média como protótipo avançado, porém ainda dependente de melhorias fortes em reprodutibilidade, testes e operação.

### Em segurança e readiness para produção
Promissor, mas ainda precisa de hardening explícito antes de ser tratado como produto exposto com confiança.

### Em debugabilidade da acurácia
A fundação já existe no estado e no workflow. O que falta é transformar isso em telemetry de primeira classe e rotina operacional de análise.

---

## 15. Evidências objetivas relevantes desta revisão

- branch atual observada: `agent_v3`;
- working tree limpo no momento da análise;
- `pytest -q` falhou na coleta por problemas de ambiente/dependências/imports;
- `src/agent/cli_session.py`, `src/agent/metrics.py`, `src/agent/orchestrator_support.py` e `src/utils/logging_setup.py` existem no repo;
- import manual de `src.agent.cli_session` funcionou fora do pytest;
- `evaluation/README.md` está desalinhado com a documentação principal mais recente;
- `.gitignore` exclui documentos estratégicos como `ARCH.md` e `ROADMAP.md`;
- `src/memory/vector_store.py` usa ChromaDB, mas isso não ficou claramente representado nas dependências lidas como contrato principal.

---

## 16. Conclusão prática

Se o objetivo for evoluir este projeto para um sistema confiável, auditável e pronto para uso mais sério, eu não começaria por trocar modelo nem por adicionar novas camadas de agente.

Eu começaria por:
- estabilizar ambiente;
- consolidar documentação e benchmark;
- transformar tracing/telemetry em recurso central;
- endurecer política de execução SQL e exposição da API;
- usar a avaliação para explicar erros, não apenas medir score final.

Esse caminho deve gerar mais ganho real de produto do que aumentar a complexidade do pipeline neste momento.
