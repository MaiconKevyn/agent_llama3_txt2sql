# ADR-003: Camada de contratos semanticos antes do SQL

Status: aceito
Data: 2026-05-22

## Contexto

Perguntas analiticas em saude dependem de granularidade, joins confiaveis, chaves candidatas, qualidade de dados e definicoes de metricas. O LLM nao deve decidir sozinho se um join e seguro ou se um campo representa a entidade pedida.

## Decisao

Criar uma camada de contratos semanticos carregada de fontes versionadas, principalmente `docs/generated`, antes da validacao e execucao SQL.

## Fontes iniciais

- `docs/generated/join_policy.csv`
- `docs/generated/candidate_keys.csv`
- `docs/generated/data_quality_checks.json`
- `docs/generated/column_catalog.csv`
- `docs/generated/ground_truth_semantic_audit.csv`

## Alternativas consideradas

- Manter contratos apenas em prompts: facil de iniciar, mas dificil de testar.
- Validar somente sintaxe SQL: insuficiente para evitar erro semantico.
- Codificar tudo em heuristicas soltas: rapido no curto prazo, mas aumenta regressao.

## Consequencias

- Joins devem ser classificados como permitidos, permitidos com caveat, audit-only ou desconhecidos.
- Caveats obrigatorios devem chegar ate a resposta final.
- Contratos novos devem ter testes unitarios e, quando forem de produto, casos de benchmark.

## Impacto em testes e avaliacao

- `join_policy.csv` deve ser exercitado por testes de loader/validator.
- Casos com `MUNIC_RES`, `CID_MORTE`, `DIAG_SECUN` e dimensoes de baixa cobertura devem verificar caveats ou bloqueio.
