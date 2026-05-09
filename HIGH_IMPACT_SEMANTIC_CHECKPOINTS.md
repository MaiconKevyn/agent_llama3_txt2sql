# High Impact Semantic Checkpoints

Objetivo: melhorar performance, generalizacao e robustez sem tunar perguntas especificas do benchmark. Cada checkpoint ataca uma classe semantica observada no ablation e deve ser validado por testes unitarios e por pelo menos uma query real no agente CLI.

## CP2 - Join Path Resolver

Status: completed

Problema:
- Perguntas sobre municipio/estado podem se referir a residencia do paciente ou local de atendimento/hospital.
- Erro de classe: usar `internacoes.MUNIC_RES` quando a pergunta pede municipio que atende/recebe pacientes ou localizacao do hospital.

Implementacao:
- Detectar contexto de atendimento/hospital: `atende`, `atendem`, `recebe`, `localizacao do hospital`, `onde ficam hospitais`, `cidade do hospital`.
- Enriquecer `SemanticPlan` com dimensao contextual `municipio_hospital` ou `estado_hospital`.
- Adicionar constraint generica de join path hospitalar.
- Validar SQL contra o caminho:
  - `internacoes.CNES -> hospital.CNES`
  - `hospital.MUNIC_MOV -> municipios.codigo_6d`
- Gerar guidance claro quando SQL usar residencia em contexto de atendimento.

Validacao:
- Unit: plano para "municipios que atendem mais pacientes" exige caminho hospitalar.
- Unit: validator rejeita `MUNIC_RES` para pergunta de atendimento.
- CLI: "Quais sao os 10 municipios que atendem mais pacientes?"

Resultado:
- Unit tests adicionados e passando.
- CLI validado: SQL usou `internacoes -> hospital -> municipios` via `MUNIC_MOV` e retornou 10 linhas.

## CP4 - Top-N Por Grupo Validator

Status: completed

Problema:
- Queries hard com "top N por estado/grupo" podem usar `LIMIT N` global ou ranking sem filtro de suporte minimo.
- Erro de classe: top-N por grupo e metricas medias em entidades de alta cardinalidade sem `HAVING COUNT(*) > N`.

Implementacao:
- Melhorar deteccao de top-N em frases como `os 10 municipios`, `as 3 cidades`, `3 hospitais`.
- Exigir janela `ROW_NUMBER/RANK/DENSE_RANK OVER (PARTITION BY grupo)` para top-N por grupo.
- Para ranking por media/taxa em entidade de alta cardinalidade, exigir suporte minimo quando a pergunta nao declarar outro threshold.
- Promptar macro de top-N por grupo com `HAVING COUNT(*) > 100` para ranking de media/taxa por hospital/municipio.

Validacao:
- Unit: plano para "3 hospitais com maior custo medio de UTI por estado" exige top-N por grupo e suporte minimo.
- Unit: validator rejeita ranking por media hospitalar sem `HAVING COUNT(*) > 100`.
- CLI: "Quais sao os 3 hospitais com maior custo medio de UTI por estado (MA e RS)?"

Resultado:
- Unit tests adicionados e passando.
- CLI validado: SQL usou CTE agregada, `HAVING COUNT(*) > 100`, `ROW_NUMBER() OVER (PARTITION BY estado)` e `WHERE rn <= 3`.

## CP5 - Domain Code Filters

Status: completed

Problema:
- Dimensoes de dominio possuem codigos invalidos/sem informacao que nao devem entrar em analises quando a pergunta pede grupos validos.
- Erro de classe: `INSTRU=0` aparecendo em mortalidade por nivel de instrucao.

Implementacao:
- Centralizar filtros de dominio validos.
- Para dimensao `instrucao`, exigir:
  - join `instrucao`
  - `i."INSTRU" IS NOT NULL`
  - `i."INSTRU" != 0`
- Para analises de taxa/media por raca, permitir regra semelhante sem quebrar distribuicoes que pedem composicao.

Validacao:
- Unit: plano de taxa por nivel de instrucao inclui filtro de codigo valido.
- Unit: validator rejeita SQL agrupado por instrucao sem excluir `0`.
- CLI: "Qual e a taxa de mortalidade por nivel de instrucao no estado do RS, considerando apenas grupos com mais de 1000 internacoes?"

Resultado:
- Unit tests adicionados e passando.
- CLI validado: SQL juntou `instrucao`, excluiu `INSTRU IS NULL` e `INSTRU = 0`, preservou denominador por agregacao condicional e aplicou `HAVING COUNT(*) > 1000`.

## CP6 - Socioeconomico Metric Resolver

Status: completed

Problema:
- `socioeconomico` e long-format; toda query deve resolver `metrica`.
- Erro de classe: mortalidade infantil media usa metrica errada ou tenta calcular a partir de `internacoes`.

Implementacao:
- Criar resolver deterministicamente mapeado para metricas conhecidas.
- `mortalidade infantil` -> `metrica = 'mortalidade_infantil_1ano'`.
- Plano deve usar `base_grain=municipio_ano_metrica`, metric `mortalidade_infantil_1ano`, filtro `metrica`.
- Validator deve rejeitar socioeconomico sem filtro de metrica ou com metrica incompatível quando o plano declara uma metrica.

Validacao:
- Unit: plano para "taxa de mortalidade infantil media" resolve `mortalidade_infantil_1ano`.
- Unit: validator rejeita `bolsa_familia_total` para mortalidade infantil.
- CLI: "Qual a taxa de mortalidade infantil media no Brasil?"

Resultado:
- Unit tests adicionados e passando.
- CLI validado: SQL usou somente `socioeconomico` e filtrou `metrica = 'mortalidade_infantil_1ano'`.
