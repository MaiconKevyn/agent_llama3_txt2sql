# Relatório de Revisões — bare_conf.tex

**Paper:** A Conversational Agent for Public Health Data Analytics
**Venue:** CBMS (Computer-Based Medical Systems) — formato IEEE Conference
**Arquivo principal:** `docs/CBMS/bare_conf.tex`
**Bibliografia:** `docs/CBMS/sample-base.bib`

---

## Histórico de Revisões

---

### [REV-01] — 2026-02-20 — Remoção das afirmações de "governance-first"

**Responsável:** Revisão via Claude Code

#### Contexto e Motivação

O paper foi originalmente redigido com uma narrativa "governance-first", ou seja, a ideia central era que a aplicação de práticas de governança de dados (modelagem dimensional, padronização de valores, constraints de integridade, enriquecimento de metadados) seria o principal fator responsável pela confiabilidade do agente Text-to-SQL.

Essa narrativa foi identificada como **incompatível com o escopo real do paper**, por duas razões:

1. **Foco do paper:** O paper trata do **desenvolvimento do agente conversacional** (pipeline LangGraph, schema-aware prompting, loop de validação e auto-reparo) e da **metodologia de avaliação** (benchmark de 52 queries em português, métricas CM e EX). A construção e modelagem do banco de dados é trabalho separado, desenvolvido por outra integrante da equipe, e não é uma contribuição direta deste paper.

2. **Ausência de evidência experimental:** O paper não realiza nenhum experimento comparativo que demonstre que a governança de dados melhora a performance do agente (ex: agente com vs. sem governança). Afirmar isso sem evidência constituiria uma claim não suportada, o que poderia ser rejeitado por revisores.

#### Alterações Realizadas

Todas as alterações foram feitas no arquivo `bare_conf.tex`. As ocorrências foram identificadas com busca pela palavra-chave `governance` e variantes.

---

**1. Introduction — Linha 409**

| | Texto |
|---|---|
| **Antes** | `"In real-world settings like DATASUS, where governance is incomplete, Text-to-SQL agents face cascading failures..."` |
| **Depois** | `"In real-world settings like DATASUS, where schemas are complex, values are domain-coded, and documentation is sparse—posing significant challenges for Text-to-SQL agents..."` |

*Razão:* A caracterização do DATASUS como "incomplete governance" implica que a solução é melhorar a governança. O texto foi reescrito para descrever os desafios técnicos concretos (schemas complexos, valores codificados, documentação escassa), que são fatos observáveis e não afirmam nenhuma relação causal com a performance do agente.

---

**2. Introduction — Linha 409 (final do parágrafo)**

| | Texto |
|---|---|
| **Antes** | `"The core challenge is not merely translating language into SQL, but ensuring the underlying data infrastructure supports reliable query generation and execution."` |
| **Depois** | `"The core challenge is adapting Text-to-SQL pipelines to the specific characteristics of domain-specific health databases."` |

*Razão:* A frase original posicionava a "infraestrutura de dados" (i.e., governança) como o desafio central, deslocando o foco do agente. A nova frase mantém o desafio correto: adaptar Text-to-SQL a um domínio específico.

---

**3. Introduction — Linha 411 (nova adição)**

O comentário vazio `% objetivo` foi substituído por um parágrafo completo de objetivo, ausente na versão anterior. O parágrafo apresenta: (a) o agente desenvolvido, (b) a tecnologia base (LangGraph), (c) o dataset (SIH-RD/SUS, RS, 2008–2023), (d) o público-alvo (profissionais de saúde) e (e) a metodologia de avaliação (52 queries, CM e EX).

*Razão:* A ausência do objetivo na introdução era uma lacuna crítica — o leitor terminava a introdução sem saber o que o paper propunha fazer.

---

**4. Related Work — Linha 423**

| | Texto |
|---|---|
| **Antes** | `"We operationalize a governance-first pipeline with a Portuguese NL→SQL agent for DATASUS, tying governance artifacts (tests, dictionaries, constraints) to agent robustness."` |
| **Depois** | `"We address this gap by presenting a Portuguese NL→SQL conversational agent for DATASUS, built over a structured health data warehouse, with schema-aware prompting and a validation-and-repair pipeline, evaluated on a domain-specific benchmark of 52 Portuguese healthcare queries."` |

*Razão:* "governance-first pipeline" e "governance artifacts" são termos que afirmam explicitamente que a abordagem de governança é o diferencial do trabalho. A nova frase posiciona corretamente as contribuições: o **agente**, a **abordagem técnica** (schema-aware prompting + validação) e o **benchmark de avaliação**.

---

**5. Proposed Approach → Conversational Agent — Linha 439**

| | Texto |
|---|---|
| **Antes** | `"...against a governed health data warehouse."` |
| **Depois** | `"...against a structured health data warehouse."` |

*Razão:* "governed" qualifica o warehouse de forma que implica que a governança é uma característica relevante para o desempenho do agente. "structured" é neutro e tecnicamente correto.

---

**6. Proposed Approach → Conversational Agent — Linha 443**

| | Texto |
|---|---|
| **Antes** | `"...each stage receives governance-enriched metadata (table schemas, column types, value ranges, foreign key relationships)..."` |
| **Depois** | `"...each stage receives domain-specific metadata (table schemas, column types, value ranges, foreign key relationships)..."` |

*Razão:* "governance-enriched" atribui o enriquecimento dos metadados à governança. O que o agente realmente recebe é **metadados de domínio** (schemas, tipos, FKs) — informação estrutural do banco, não um artefato de governança.

---

**7. Proposed Approach → Conversational Agent — Linha 443 (final do parágrafo)**

| | Texto |
|---|---|
| **Antes** | `"This demonstrates that combining systematic data governance with targeted prompt engineering enables reliable SQL synthesis without model fine-tuning."` |
| **Depois** | `"This demonstrates that combining schema-aware, domain-specific prompt engineering with a validation-and-repair loop enables reliable SQL synthesis without model fine-tuning."` |

*Razão:* A afirmação original creditava a "systematic data governance" como fator de desempenho, sem evidência experimental. A nova frase identifica os fatores técnicos corretos: **prompt engineering schema-aware** e o **loop de validação e reparo** — ambos componentes do agente, mensuráveis e descritos no paper.

---

**8. Results and Discussion — Linha 540**

| | Texto |
|---|---|
| **Antes** | `"...an intended effect of the governance-aware validation layer."` |
| **Depois** | `"...an intended effect of the validation-and-repair layer."` |

*Razão:* "governance-aware" é um adjetivo sem base nos resultados apresentados. O componente correto é a "validation-and-repair layer", que é o que o paper descreve tecnicamente.

---

**9. Conclusion — Linhas 551–553 (reescrita)**

Esta foi a alteração mais extensa. Os dois parágrafos da conclusão foram integralmente reescritos.

| | Resumo do conteúdo |
|---|---|
| **Antes** | Afirmava que a abordagem "governance-first" (data quality engineering antes do deployment) é o que permite o agente funcionar; citava "governance investments (dimensional modeling, value standardization, integrity constraints, metadata enrichment)" como responsáveis pela confiabilidade; concluía com chamado a "policy and technical investments in data quality". |
| **Depois** | Descreve o agente desenvolvido, sua arquitetura (LangGraph + schema-aware prompting + self-repair), os resultados (82.1% EX, 68.1% CM, 100% completion), e posiciona o trabalho como baseline reprodutível para Text-to-SQL em português sobre dados públicos de saúde no Brasil. |

*Razão:* A conclusão anterior afirmava uma relação causal (governança → confiabilidade do agente) não demonstrada experimentalmente. A nova conclusão reporta os resultados observados e posiciona as contribuições reais: o **agente**, a **metodologia de avaliação** e o **baseline** estabelecido para o domínio.

---

#### Estado do Paper após REV-01

| Seção | Status | Observações |
|---|---|---|
| Título | Completo | Pode ser refinado futuramente |
| Abstract | **Pendente** | Ainda com placeholder |
| Introduction | Melhorado | Objetivo adicionado; narrativa corrigida |
| Related Work | Melhorado | Posicionamento corrigido |
| Data Gathering | **Pendente** | A ser preenchido pela colega responsável pelo banco |
| Database Modeling | **Pendente** | A ser preenchido pela colega responsável pelo banco |
| Conversational Agent | Melhorado | Linguagem corrigida; conteúdo técnico preservado |
| Evaluation Methodology | Sem alterações | Seção sólida |
| Results & Discussion | Melhorado | "governance-aware" removido |
| Conclusion | Reescrita | Narrativa alinhada ao foco real do paper |
| Contributions | **Pendente** | Placeholder `....` |
| Limitations | **Pendente** | Placeholder `...` |
| Future Work | **Pendente** | Placeholder `...` |

---

### [REV-02] — 2026-02-20 — Resposta aos feedbacks de revisão: métrica "Success" e alegações de confiabilidade

**Responsável:** Revisão via Claude Code
**Origem:** 3 feedbacks recebidos de revisor externo (analisados e priorizados pelos autores)

#### Contexto e Motivação

Foram recebidos três feedbacks de revisão. Os feedbacks 1 e 2 apontaram problemas concretos e imediatos no texto; o feedback 3 foi considerado **já endereçado pela REV-01** e é registrado aqui apenas para rastreabilidade.

---

##### Feedback 1 — Métrica "Success: 100%" gera confusão com Execution Accuracy

**Problema apontado:** A tabela de resultados continha uma coluna "Success" com valor constante de 100% em todos os tiers. O revisor observou que essa métrica — que mede apenas se o pipeline terminou sem crash ou timeout — pode ser confundida com acurácia. Um query pode pontuar 100% em "Success" e 0% em EX simultaneamente, pois "sucesso" mede completude do workflow, não correção do resultado.

**Análise:** Feedback inteiramente válido. A coluna "Success" é uma métrica constante (100% em todas as linhas), portanto não contribui para comparação entre tiers e sua presença na tabela ao lado de CM e EX cria ambiguidade real, especialmente num venue de sistemas médicos (CBMS) onde leitores são sensíveis à distinção entre "o sistema executou" e "o sistema acertou".

**Alterações realizadas:**

**1a. Tabela — Remoção da coluna Success**

| | |
|---|---|
| **Antes** | `\begin{tabular}{lcccc}` com colunas: Tier, Queries, CM, EX, Success |
| **Depois** | `\begin{tabular}{lccc}` com colunas: Tier, Queries, CM, EX |

Todas as linhas da tabela tiveram o valor `& 100\%` removido (Simple, Moderate, Complex, Overall).

*Razão:* Coluna constante não discrimina tiers e induz confusão. O dado é mais bem reportado em prosa com definição explícita.

**1b. Parágrafo de Results — Redefinição em prosa com separação explícita**

| | Texto |
|---|---|
| **Antes** | `"The agent completed all workflows (100%) and achieved 82.1% EX with 68.1% CM..."` |
| **Depois** | `"All 52 queries were executed to completion without runtime errors or timeouts (pipeline completion rate: 100%). This metric reflects workflow stability only---it indicates that the agent always produced an output, not that the output was correct. On the accuracy metrics, the agent achieved 82.1% EX with 68.1% CM..."` |

*Razão:* A separação explícita entre pipeline completion rate (estabilidade) e métricas de acurácia (CM, EX) elimina a ambiguidade. A frase "not that the output was correct" é deliberadamente direta para antecipar qualquer interpretação equivocada.

---

##### Feedback 2 — Alegações de "confiabilidade" contradizem taxa de erro de 41.7% em queries complexas

**Problema apontado:** O paper usava "reliable" e "trustworthy" para descrever o sistema, enquanto os dados reportam 58.3% de EX em queries complexas — 41.7% de erro. Em contextos de saúde, queries complexas são usadas para decisões de alto impacto. O revisor apontou ausência de discussão sobre as consequências desses erros.

**Análise:** Feedback crítico e inteiramente válido. "Reliable" pressupõe consistência e correção — incompatível com 41.7% de erro. Em sistemas médicos, resultados incorretos são frequentemente mais perigosos do que ausência de resposta, pois retornam números plausíveis mas errôneos que podem orientar decisões sem disparar alertas.

**Alterações realizadas:**

**2a. Proposed Approach → Conversational Agent**

| | Texto |
|---|---|
| **Antes** | `"...enables reliable SQL synthesis without model fine-tuning."` |
| **Depois** | `"...enables effective SQL synthesis without model fine-tuning."` |

*Razão:* "reliable" implica garantia de correção. "effective" descreve que a abordagem funciona bem (82.1% EX overall) sem prometer consistência absoluta.

**2b. Conclusion — primeiro parágrafo**

| | Texto |
|---|---|
| **Antes** | `"...demonstrating that a modular, self-correcting pipeline can support reliable analytical querying..."` |
| **Depois** | `"...demonstrating the feasibility of NL-driven analytical querying over domain-specific health databases without model fine-tuning."` |

*Razão:* "reliable analytical querying" é forte demais para um sistema com 58.3% EX em queries complexas. "demonstrating the feasibility" é calibrado: o paper prova que é possível, não que é confiável para produção.

**2c. Conclusion — segundo parágrafo**

| | Texto |
|---|---|
| **Antes** | `"...enabling evidence-based decision-making by healthcare professionals without requiring SQL expertise."` |
| **Depois** | `"...supporting healthcare professionals in exploratory data analysis without requiring SQL expertise, while reinforcing the importance of human validation for high-stakes analytical outputs."` |

*Razão:* "evidence-based decision-making" implica que os resultados são diretamente acionáveis para decisões clínicas, o que não é suportado pelos resultados. A nova frase reposiciona o sistema como ferramenta de **exploração analítica assistida**, com validação humana explicitamente requerida para contextos de alto impacto.

**2d. Results and Discussion — Novo parágrafo sobre implicações dos erros**

Adicionado parágrafo após a análise por tier, explicitando as implicações do 41.7% de erro em queries complexas no contexto de saúde pública:

> *"The 41.7% error rate on Complex queries warrants careful consideration in healthcare contexts. Complex analytical queries—multi-table joins with grouped aggregations across demographic, geographic, or socioeconomic dimensions—are precisely those most likely to inform resource allocation, epidemiological investigations, and policy decisions. Crucially, incorrect queries do not silently fail: they return plausible but erroneous numbers, which may be more harmful than no answer at all. These results indicate that the current system is best used as an analytical assistant that accelerates query formulation, with outputs subject to domain expert validation before operational use. Autonomous deployment in high-stakes decision-making contexts is not appropriate at the current accuracy level."*

*Razão:* Responde diretamente ao ponto do revisor. O parágrafo (a) reconhece o problema, (b) justifica por que queries complexas são críticas em saúde pública, (c) destaca que erros plausíveis são piores que falhas silenciosas, e (d) define claramente o papel adequado do sistema como assistente com supervisão humana.

---

##### Feedback 3 — Contribuição sobre governance sem evidência experimental (registrado para rastreabilidade)

**Problema apontado:** O revisor indicou que a contribuição "tying governance artifacts to downstream agent robustness" exigiria um ablation study para ser válida como contribuição experimental.

**Status:** **Endereçado preventivamente pela REV-01.** Toda a narrativa governance-first foi removida antes deste feedback ser processado. A seção de contribuições permanece como placeholder e, quando preenchida, deverá listar apenas: (1) o agente com pipeline LangGraph, (2) o benchmark de 52 queries em português, (3) o baseline de resultados. A ideia de "tying governance artifacts to robustness" pode ser reposicionada como trabalho futuro (ablation study).

---

#### Estado do Paper após REV-02

| Seção | Status | Observações |
|---|---|---|
| Título | Completo | Pode ser refinado futuramente |
| Abstract | **Pendente** | Placeholder |
| Introduction | Completo | Objetivo adicionado; narrativa corrigida (REV-01) |
| Related Work | Completo | Posicionamento corrigido (REV-01) |
| Data Gathering | **Pendente** | A ser preenchido pela colega do banco |
| Database Modeling | **Pendente** | A ser preenchido pela colega do banco |
| Conversational Agent | Completo | "reliable" → "effective" (REV-02) |
| Evaluation Methodology | Sem alterações | Seção sólida |
| Results & Discussion | Melhorado | Coluna Success removida; parágrafo de implicações adicionado (REV-02) |
| Conclusion | Melhorado | "reliable" e "evidence-based decision-making" qualificados (REV-02) |
| Contributions | **Pendente** | Não reinstaurar governance claims |
| Limitations | **Preenchido** | Ausência de baselines; sem domain specialists; escopo geográfico restrito |
| Future Work | **Preenchido** | Direct prompting baseline; modelos maiores; ablation; domain specialists |

---

### [REV-03] — 2026-02-20 — Resposta ao feedback: ausência de comparações com baselines

**Responsável:** Revisão via Claude Code
**Origem:** Feedback de revisor externo

#### Contexto e Motivação

O revisor identificou que 82.1% de EX é um número sem contexto interpretável na ausência de comparações com sistemas alternativos ou abordagens mais simples. Sem baselines, não é possível determinar se o resultado é bom, mediano ou ruim. O revisor sugeriu: (1) sistemas Text-to-SQL alternativos no mesmo banco, (2) abordagens mais simples sem orquestração, (3) LLMs alternativos, e como mínimo: (a) direct prompting sem LangGraph, (b) mesmo agente em "ungoverned data".

#### Análise de Viabilidade por Sugestão

| Sugestão | Viável agora? | Decisão |
|---|---|---|
| Sistema alternativo adaptado ao mesmo banco | Não — nenhum existe para DATASUS em português | Impossível; reconhecido como gap do campo |
| Direct prompting sem LangGraph | Sim — requer rodar experimento | Listado como Future Work prioritário |
| LLMs alternativos (GPT-4, Claude, Llama 70b) | Parcialmente — requer API e execução | Listado como Future Work |
| Mesmo agente em "ungoverned data" | **Moot** — sugestão baseada na narrativa governance-first removida na REV-01 | Não aplicável |

**Conclusão:** A resposta ideal exige rodar experimentos (especialmente o baseline de direct prompting). O que pode ser feito agora — sem experimentos — é posicionar corretamente os resultados no texto e preencher os placeholders de Limitations e Future Work com compromissos claros.

#### Alterações Realizadas

**3a. Results and Discussion — Contextualização do 82.1% EX (linha 540)**

Adicionada frase ao primeiro parágrafo de resultados:

| | Texto |
|---|---|
| **Antes** | `"...an EX--CM gap of 15.0 percentage points. This gap is consistent with..."` |
| **Depois** | `"...an EX--CM gap of 15.0 percentage points. As no prior Text-to-SQL system has been evaluated on Portuguese analytical queries over DATASUS microdata, these results constitute a first reference point for this domain rather than a comparison against established systems; the absence of comparative baselines is acknowledged as a limitation of this work (Section~\ref{sec:conclusions}). This gap is consistent with..."` |

*Razão:* Antecipar proativamente a ausência de baselines no ponto em que os números são apresentados, redirecionando o leitor para Limitations antes que a interpretação equivocada ocorra.

**3b. Limitations — Placeholder preenchido**

O placeholder `"As a limitation, ..."` foi substituído por parágrafo substantivo cobrindo:
- Ausência de baselines comparativos (main limitation) — direct prompting sem pipeline, LLMs alternativos
- Ausência de domain specialists na criação do benchmark
- Escopo geográfico/temporal restrito (RS, 2008–2023)

**3c. Future Work — Placeholder preenchido**

O placeholder `"For future work, we will ..."` foi substituído por três eixos concretos:
1. **Baselines comparativos** no mesmo conjunto de 52 queries: (i) direct prompting Llama 3.1:8b sem LangGraph, (ii) modelos maiores (GPT-4, Claude Sonnet, Llama 3.1:70b)
2. **Ablation studies** por componente do pipeline (schema-aware prompting, validation loop, self-repair)
3. **Benchmark ampliado** com domain specialists e cobertura de outros estados e sistemas além do SIH-RD

*Razão:* Comprometer-se com experimentos futuros específicos é mais crível que afirmações vagas; mostra ao revisor que o gap foi compreendido e há um plano concreto. Esses experimentos são diretamente implementáveis com a infraestrutura existente do projeto (o benchmark de 52 queries já existe).

#### Nota sobre o Baseline de Direct Prompting

O baseline mais crítico — direct prompting sem LangGraph — é implementável com o código existente. Consiste em:
1. Para cada uma das 52 queries do benchmark, enviar ao Llama 3.1:8b apenas: schema das tabelas relevantes + pergunta em português
2. Medir CM e EX com o mesmo avaliador
3. Comparar com os resultados do pipeline completo

Caso esse experimento seja realizado, os resultados devem ser adicionados como nova coluna na tabela (ex: "Direct" vs "Pipeline") e a discussão expandida para interpretar a diferença de desempenho.

---

#### Estado do Paper após REV-03

| Seção | Status | Observações |
|---|---|---|
| Título | Completo | Pode ser refinado futuramente |
| Abstract | **Pendente** | Placeholder |
| Introduction | Completo | REV-01 |
| Related Work | Completo | REV-01 |
| Data Gathering | **Pendente** | Colega do banco |
| Database Modeling | **Pendente** | Colega do banco |
| Conversational Agent | Completo | REV-01, REV-02 |
| Evaluation Methodology | Sem alterações | Seção sólida |
| Results & Discussion | Completo | Contextualização de baselines adicionada (REV-03) |
| Conclusion | Completo | REV-01, REV-02 |
| Contributions | **Pendente** | Não reinstaurar governance claims |
| Limitations | **Preenchido** | Ausência de baselines; sem domain specialists; sample size; escopo restrito |
| Future Work | **Preenchido** | Direct prompting; modelos maiores; ablation; domain specialists |

---

### [REV-04] — 2026-02-20 — Resposta a três novos feedbacks: poder estatístico, controle de condições, e escopo positivo

**Responsável:** Revisão via Claude Code
**Origem:** 3 feedbacks adicionais de revisor externo

---

#### Feedback 1 — Poder estatístico e validade do benchmark

**Problema apontado:** 52 queries criadas pela equipe, sem validação por especialistas de domínio, é insuficiente para inferência estatística robusta. Revisor sugere expandir e/ou ao menos reconhecer como limitação.

**Análise:** Parcialmente coberto antes desta revisão — o paper já mencionava ausência de domain specialists em Evaluation Methodology (L465) e Limitations. O que estava **faltando**: menção explícita ao problema de sample size e sua implicação para confiabilidade estatística das estimativas por tier (especialmente Complex com apenas 14 queries).

**Alterações realizadas:**

**1a. Limitations — Frase sobre poder estatístico adicionada**

| | Texto |
|---|---|
| **Antes** | `"The evaluation dataset was created by the research team without participation of clinical domain specialists, which may affect query diversity and difficulty distribution. Finally, the evaluation covers..."` |
| **Depois** | Inserida frase entre as duas: `"Moreover, the 52-query set is modest in size; tier-level estimates—particularly for the Complex tier (14 queries)—should be interpreted with caution, as the small sample size limits the statistical reliability of per-tier conclusions and precludes robust significance testing."` |

*Razão:* O revisor pediu explicitamente que "strong conclusions" fossem evitadas. Nomear o problema com precisão (14 Complex queries, "precludes robust significance testing") é mais crível do que uma ressalva genérica.

**Sem alteração em Evaluation Methodology:** A frase de L465 já dizia "This choice reflects the current stage of the project; the participation of domain specialists...is planned as future work" — suficiente para antecipar o problema. Não duplicamos.

---

#### Feedback 2 — Ausência de condições de controle para causalidade governance-first

**Problema apontado:** O revisor argumentou que a claim "governance-first causally improves Text-to-SQL" requer comparação controlada (agente em dados não-governados vs. governados). Sugeriu ou fazer o experimento ou reposicionar como resource/application paper.

**Análise:** **Este feedback foi pre-emptivamente endereçado pela REV-01.** O paper não faz mais qualquer afirmação causal sobre governança desde REV-01. O reposicionamento sugerido pelo revisor como opção (2) — "resource/application paper documenting infrastructure development" — é exatamente o que o paper é agora: apresenta o agente, o benchmark e os resultados sem claims causais sobre governança. Nenhuma alteração adicional necessária.

**Registrado aqui para rastreabilidade.**

---

#### Feedback 3 — Positivo: valida o gap, nota escopo limitado

**Natureza:** Feedback positivo. O revisor reconhece: (a) primeiro sistema Text-to-SQL em português para DATASUS, (b) necessidade operacional genuína (epidemiologistas, analistas, pesquisadores de políticas), (c) SUS com 210+ milhões de pessoas. Critica apenas o escopo limitado (estado único, subsistema único).

**Análise:** A crítica de escopo já estava coberta em Limitations e Future Work. A oportunidade identificada foi usar a **escala do SUS** mencionada pelo revisor para fortalecer a motivação na Introduction, onde DATASUS era introduzido sem contextualização de importância.

**Alterações realizadas:**

**3a. Introduction (L409) — Escala do SUS adicionada**

| | Texto |
|---|---|
| **Antes** | `"In real-world settings like DATASUS, schemas are complex, values are domain-coded..."` |
| **Depois** | `"Real-world health information systems present fundamentally different conditions. DATASUS is the public data platform of Brazil's Unified Health System (SUS), which provides universal healthcare to over 210 million people~\cite{datasus_site}; its schemas are complex, values are domain-coded..."` |

*Razão:* A introdução não contextualizava por que DATASUS importa. A escala (210+ milhões de pessoas) e a missão (sistema universal de saúde) tornam o problema imediatamente legível para revisores internacionais, fortalecem o argumento de impacto potencial, e aproveitam a própria argumentação do revisor positivo.

---

#### Estado do Paper após REV-04

| Seção | Status | Observações |
|---|---|---|
| Título | Completo | Pode ser refinado |
| Abstract | **Pendente** | Placeholder |
| Introduction | Completo | Escala do SUS adicionada (REV-04) |
| Related Work | Completo | REV-01 |
| Data Gathering | **Pendente** | Colega do banco |
| Database Modeling | **Pendente** | Colega do banco |
| Conversational Agent | Completo | REV-01, REV-02 |
| Evaluation Methodology | Sem alterações | Já mencionava domain specialists |
| Results & Discussion | Completo | REV-02, REV-03 |
| Conclusion | Completo | REV-01, REV-02 |
| Contributions | **Pendente** | Não reinstaurar governance claims |
| Limitations | Completo | Sample size adicionado (REV-04); todos os pontos cobertos |
| Future Work | Completo | REV-03 |

---
