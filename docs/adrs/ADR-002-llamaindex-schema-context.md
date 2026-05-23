# ADR-002: LlamaIndex para recuperacao de contexto de schema

Status: aceito
Data: 2026-05-22

## Contexto

O banco SIHRD5/DataSUS tem muitas tabelas e colunas, com nomes tecnicos e relacoes semanticas especificas. Incluir todo o schema em cada prompt aumenta custo, latencia e ruido.

## Decisao

Usar LlamaIndex para recuperar contexto de schema relevante, combinado com heuristicas e validadores deterministas.

## Alternativas consideradas

- Prompt com schema completo: simples, mas caro e ruidoso.
- Apenas heuristicas manuais: rapido, mas fragil para perguntas variadas.
- Apenas selecao LLM sem indice: menos infraestrutura, mas menos reprodutivel.

## Consequencias

- A recuperacao de schema nao e fonte unica de verdade; ela deve ser validada contra o banco e contratos gerados.
- O modo de selecao deve expor confidence, tabelas candidatas e tabelas validadas.
- Mudancas em `docs/generated` e no banco devem considerar rebuild/validacao do indice.

## Impacto em testes e avaliacao

- Testes devem garantir que tabelas removidas ou colunas inexistentes nao entram no contexto ativo.
- Benchmarks devem registrar tabelas selecionadas, modo de recuperacao e falhas de selecao.
