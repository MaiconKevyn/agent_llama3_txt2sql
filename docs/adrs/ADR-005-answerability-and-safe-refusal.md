# ADR-005: Separar respondibilidade de sucesso tecnico

Status: aceito
Data: 2026-05-22

## Contexto

Nem toda pergunta deve gerar SQL. Perguntas sobre medicamentos, exames laboratoriais ou vacinacao podem estar fora do schema. Perguntas ambiguas podem exigir clarificacao. Esses comportamentos sao sucesso de produto quando ocorrem corretamente, mesmo sem consulta executada.

## Decisao

Separar `technical_success` de `answerability`.

Valores de `answerability`:

- `answerable`
- `unanswerable_schema`
- `requires_clarification`
- `blocked_policy`
- `technical_error`

## Alternativas consideradas

- Usar apenas `success`: simples, mas confunde recusa correta com erro.
- Tratar toda ausencia de SQL como falha: penaliza comportamento seguro.
- Tratar toda resposta textual como sucesso: mascara falhas tecnicas.

## Consequencias

- Avaliadores e UI devem mostrar recusa segura como comportamento esperado.
- Logs precisam distinguir erro tecnico de pergunta fora do escopo.
- Benchmarks devem avaliar answerability esperada, nao apenas SQL gerado.

## Impacto em testes e avaliacao

- Casos out-of-schema devem exigir `technical_success=True` e `answerability=unanswerable_schema`.
- Casos ambiguos devem exigir `technical_success=True` e `answerability=requires_clarification`.
- Falhas de banco, sintaxe ou runtime continuam sendo `technical_error`.
