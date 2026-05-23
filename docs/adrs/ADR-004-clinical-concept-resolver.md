# ADR-004: Resolver conceitos clinicos por catalogo versionado

Status: aceito
Data: 2026-05-22

## Contexto

Usuarios perguntam por conceitos como covid, pneumonia, diabetes, hipertensao, neoplasias e doencas cardiovasculares. Esses termos precisam virar filtros CID ou procedimentos de forma auditavel.

## Decisao

Usar um catalogo versionado de conceitos clinicos em `src/semantic/concepts/clinical_concepts_v1.yaml`, carregado por resolver deterministico antes da geracao SQL.

## Alternativas consideradas

- Deixar o LLM escolher codigos CID: alto risco de erro e baixa auditabilidade.
- Manter listas CID escondidas em macros SQL: funciona localmente, mas dificulta revisao.
- Exigir que todo usuario informe codigos CID: seguro, mas ruim para produto.

## Consequencias

- Todo conceito clinico suportado deve declarar fonte, versao, campo, operador, valores e caveat.
- Conceitos desconhecidos devem pedir clarificacao ou recusar, nao inventar filtro.
- Adicoes ao catalogo precisam de testes e casos de benchmark quando relevantes.

## Impacto em testes e avaliacao

- Testes unitarios devem cobrir cada conceito principal.
- Benchmarks devem incluir familias de doencas sem overfit em uma unica pergunta.
- Relatorios devem permitir rastrear qual versao do catalogo gerou o filtro.
