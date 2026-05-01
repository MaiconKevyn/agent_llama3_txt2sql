# TODO — Paper: A Conversational Agent for Public Health Data Analytics

**Venue:** CBMS (Computer-Based Medical Systems)
**Arquivo:** `docs/CBMS/bare_conf.tex`

> Este arquivo rastreia tarefas pendentes para completar ou fortalecer o paper.
> Cada tarefa indica origem (feedback ou decisão interna), o que fazer concretamente e o status atual.
> Quando uma tarefa for concluída, atualizar o status e registrar a alteração no `report.md`.

---

## Legenda de Status

| Símbolo | Significado |
|---|---|
| `[ ]` | Pendente |
| `[~]` | Em andamento |
| `[x]` | Concluído |

---

## Tarefas Experimentais

Tarefas que requerem execução de código e geração de novos resultados.

---

### TASK-EXP-01 — Implementar baseline de direct prompting

**Status:** `[ ]`
**Origem:** Feedback de revisor — *"Absence of Baseline Comparisons Renders Results Uninterpretable"*
**Prioridade:** Alta — é o único baseline que pode ser implementado com a infraestrutura existente

**O que fazer:**
Para cada uma das 52 queries do benchmark de avaliação, enviar ao Llama 3.1:8b apenas:
- O schema das tabelas relevantes (colunas, tipos, chaves estrangeiras)
- A pergunta em português

...sem qualquer orquestração LangGraph: sem table selection automático, sem validation loop, sem self-repair. Apenas um único prompt → resposta SQL → execução → medição.

**Métricas a calcular:** CM e EX por tier (Simple / Moderate / Complex) e Overall — exatamente as mesmas da tabela atual.

**Como incorporar ao paper:**
- Adicionar coluna "Direct" na tabela de resultados (ao lado de CM e EX atuais, que passam a ser rotulados como "Pipeline")
- Expandir discussão em Results & Discussion para comparar os dois sistemas por tier
- Remover ou atualizar a frase em L540 que diz "these results constitute a first reference point...rather than a comparison against established systems"

**Referência no paper atual:** Limitations (L559) e Future Work (L561) já mencionam este experimento como trabalho futuro.

---

### TASK-EXP-02 — Avaliar modelos alternativos nas 52 queries

**Status:** `[ ]`
**Origem:** Feedback de revisor — *"Absence of Baseline Comparisons"* (sugestão de GPT-4, Claude, Llama maior)
**Prioridade:** Média — desejável mas secundário ao TASK-EXP-01

**O que fazer:**
Rodar o mesmo pipeline LangGraph (ou ao menos direct prompting) com:
- Llama 3.1:70b (via Ollama, sem custo de API)
- GPT-4o ou Claude Sonnet (via API — requer acesso e custo)

**Métricas:** CM e EX no mesmo benchmark de 52 queries.

**Como incorporar ao paper:** Nova tabela ou extensão da tabela atual com coluna por modelo.

**Dependência:** Pode ser feito em paralelo com TASK-EXP-01; porém TASK-EXP-01 é mais prioritário.

---

### TASK-EXP-03 — Ablation study por componente do pipeline

**Status:** `[ ]`
**Origem:** Feedback de revisor (Feedback 3) + análise interna
**Prioridade:** Baixa para esta versão — posicionado como Future Work no paper

**O que fazer:**
Desabilitar seletivamente cada componente do pipeline e medir impacto em EX:
- Sem schema-aware prompting (schema genérico)
- Sem SQL validation loop
- Sem self-repair step
- Combinações

**Observação:** Requer refatoração cuidadosa do código para suportar configurações parciais do pipeline. Mais adequado para versão journal ou extensão do paper.

---

## Tarefas de Escrita

Tarefas que requerem apenas redação — sem experimentos.

---

### TASK-TEX-01 — Escrever o Abstract

**Status:** `[ ]`
**Origem:** Lacuna identificada na revisão inicial do paper
**Prioridade:** Alta — o paper não pode ser submetido sem abstract

**O que o abstract deve cobrir:**
1. Problema: ausência de interfaces NL para microdados de saúde pública brasileiros
2. Abordagem: agente conversacional LangGraph com schema-aware prompting e self-repair, em português
3. Dados: SIH-RD/SUS, RS, 2008–2023
4. Avaliação: benchmark de 52 queries estratificadas (Simple/Moderate/Complex), métricas CM e EX
5. Resultados: 82.1% EX overall, 100% pipeline completion
6. Conclusão: first baseline para Text-to-SQL em português sobre DATASUS

**Restrições IEEE:** Sem citações, sem fórmulas, sem símbolos especiais. Máximo ~150 palavras.

---

### TASK-TEX-02 — Escrever a seção de Contributions

**Status:** `[ ]`
**Origem:** Placeholder `....` identificado na revisão inicial; reforçado pelo Feedback 3 do revisor
**Prioridade:** Alta

**O que incluir (3 contribuições sugeridas):**
1. O agente conversacional em português para DATASUS — pipeline LangGraph de 7 etapas com schema-aware prompting, validation e self-repair
2. O benchmark de avaliação — 52 queries em português estratificadas por complexidade com gold-standard SQL, primeiras avaliações formais de Text-to-SQL sobre microdados SIH-RD/SUS
3. O baseline de resultados reprodutível — 82.1% EX, disponível publicamente para comparação futura

**Atenção:** Não reinstaurar claims de governança (removidos na REV-01). As contribuições devem ser sobre o agente, o benchmark e os resultados — não sobre a modelagem do banco.

---

### TASK-TEX-03 — Preencher seções de Data Gathering e Database Modeling

**Status:** `[ ]`
**Origem:** Seções estruturalmente vazias; responsabilidade da colega que trabalha com o banco
**Prioridade:** Alta para submissão

**Escopo esperado (conforme alinhamento com os autores):**
- Descrição superficial mas completa: fonte dos dados (DATASUS/PySUS), cobertura temporal e geográfica, volume, etapas de pré-processamento, modelo do banco (tabelas, FKs, tipos)
- O foco do paper é o agente — essas seções devem ser concisas, não o ponto central

**Responsável:** Colega da equipe (banco de dados)

---

### TASK-TEX-05 — Expandir benchmark de avaliação com domain specialists

**Status:** `[ ]`
**Origem:** Feedback 1 — *"Evaluation Set Lacks Statistical Power and Domain Validity"*; confirmado pelo Feedback 3 positivo que elogia o gap preenchido mas nota o escopo limitado
**Prioridade:** Média — crítico para versão final ou extensão do paper

**O que fazer:**
1. Envolver ao menos um especialista clínico ou epidemiologista na criação ou validação das queries de avaliação
2. Expandir o benchmark para pelo menos 100 queries totais, com proporção maior no tier Complex (atualmente só 14 queries — insuficiente para inferência estatística robusta)
3. Incluir queries propostas pelo especialista para capturar casos de uso reais de epidemiologistas e pesquisadores de políticas de saúde

**Impacto no paper:** Substitui a ressalva atual em Limitations sobre sample size; permite afirmações estatísticas mais robustas por tier.

---

### TASK-TEX-06 — Expandir cobertura geográfica e de subsistemas

**Status:** `[ ]`
**Origem:** Feedback 3 positivo — *"Unfortunate that the application had a limited scope (single state, single subsystem)"*
**Prioridade:** Baixa para esta versão — relevante para extensão/journal

**O que fazer:**
- Testar o agente em dados de outros estados brasileiros (além do RS) para avaliar generalização
- Considerar outros subsistemas do DATASUS além do SIH-RD (ex: SIM, SINASC, SIA)

**Observação:** Já mencionado em Future Work no paper. Aqui é registrado como tarefa concreta para a próxima versão.

---

### TASK-TEX-04 — Revisar título para maior especificidade

**Status:** `[ ]`
**Origem:** Avaliação interna (nota 8/10 na revisão inicial)
**Prioridade:** Baixa — opcional

**Problema:** Título atual (*"A Conversational Agent for Public Health Data Analytics"*) é genérico demais — não menciona Text-to-SQL, DATASUS, português ou o dataset.

**Sugestão:** algo como *"A Portuguese Text-to-SQL Conversational Agent for DATASUS Public Health Microdata"* ou similar.

**Observação:** Discutir com os autores antes de alterar — o título atual pode ser preferido por ser mais amplo para o público do CBMS.

---

## Concluído

Tarefas que já foram implementadas e registradas no `report.md`.

| Task | Descrição | Revisão |
|---|---|---|
| ~~Remover narrative governance-first~~ | 9 alterações em todo o paper | REV-01 |
| ~~Adicionar objetivo na Introduction~~ | Parágrafo completo substituindo `% objetivo` | REV-01 |
| ~~Remover coluna "Success" da tabela~~ | Removida; redefinida em prosa com distinção explícita | REV-02 |
| ~~Substituir "reliable" por linguagem calibrada~~ | 2 ocorrências no Agent e Conclusion | REV-02 |
| ~~Adicionar discussão de implicações de erros~~ | Parágrafo em Results sobre 41.7% em Complex | REV-02 |
| ~~Contextualizar ausência de baselines em Results~~ | Frase adicionada em L540 | REV-03 |
| ~~Preencher Limitations~~ | 4 limitações concretas | REV-03 |
| ~~Preencher Future Work~~ | 3 eixos com experimentos específicos | REV-03 |
| ~~Adicionar escala do SUS na Introduction~~ | "210+ million people" com `\cite{datasus_site}` | REV-04 |
| ~~Adicionar limitação de poder estatístico~~ | Frase sobre 14 Complex queries em Limitations | REV-04 |
