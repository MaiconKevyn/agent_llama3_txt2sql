# Chart Readability Coverage Matrix

## Objetivo

Controlar a cobertura de testes de graficos do agente por tipo visual, shape de dado, formato numerico, risco de legibilidade e caminho de execucao.

## Matriz

| ID | Tipo | Pergunta | Shape SQL | Formato | Risco | Status |
| --- | --- | --- | --- | --- | --- | --- |
| CHART_BAR_001 | bar | Top municipios por internacoes | categoria + metrica | integer | labels longos | existente |
| CHART_LINE_001 | line | Internacoes por ano | tempo + metrica | integer | ordem temporal | existente |
| CHART_PIE_001 | pie | Mortes por sexo | categoria + metrica | integer + percent | proporcao | existente |
| CHART_SCATTER_001 | scatter | Idade media vs mortes por municipio | metrica + metrica + label | decimal + integer | tooltip e contexto | covered |
| CHART_KPI_001 | kpi | Valor total de internacoes | single metric | currency_brl | numero isolado | covered |
| CHART_BAR_HIGH_CARDINALITY_001 | bar | Municipios com muitas categorias | categoria + metrica | integer | excesso de categorias | covered |
