# ADR-001: LangGraph como workflow do agente TXT2SQL

Status: aceito
Data: 2026-05-22

## Contexto

O DataSUS Agent precisa classificar perguntas, selecionar tabelas, recuperar schema, planejar semanticamente, gerar SQL, validar, executar no DuckDB, reparar erros quando possivel e compor uma resposta final com caveats. Esse fluxo possui estado intermediario, ramos condicionais e pontos de auditoria.

## Decisao

Usar LangGraph como orquestrador principal do workflow TXT2SQL, mantendo cada etapa relevante como no verificavel do grafo.

## Alternativas consideradas

- Pipeline linear Python: mais simples, mas menos adequado para branching, retry, checkpoints e observabilidade por etapa.
- Uma chamada LLM unica: menor codigo inicial, mas insuficiente para validar SQL, aplicar contratos semanticos e recusar com seguranca.
- Agentes livres com tools sem grafo explicito: flexiveis, mas mais dificeis de auditar e testar.

## Consequencias

- O estado do agente precisa continuar estruturado e serializavel.
- Cada novo comportamento critico deve aparecer em metadata, testes ou eventos do workflow.
- Follow-ups e visualizacao devem integrar ao workflow sem bypassar validacao quando gerarem nova consulta.

## Impacto em testes e avaliacao

- Testes unitarios devem cobrir nos especificos quando possivel.
- Benchmarks devem registrar fases, tool calls, SQL final, answerability e latencia.
- Erros esperados, como recusas seguras e clarificacoes, devem ser separados de falhas tecnicas.
