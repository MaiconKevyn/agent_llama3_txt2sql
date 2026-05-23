# ADR-006: Camada de visualizacao e follow-up sem contaminar o core TXT2SQL

Status: aceito
Data: 2026-05-22

## Contexto

O chatbot precisa responder perguntas analiticas e tambem permitir pedidos como "faca um grafico disso" ou "e em 2022?". Essas capacidades dependem de contexto de sessao, mas nao devem substituir validacao SQL nem poluir a tela principal.

## Decisao

Manter uma camada de follow-up e visualizacao em torno do orquestrador:

- pedidos de grafico sobre ultimo resultado usam cache de sessao e geram apenas especificacao visual;
- follow-ups textuais curtos sao reescritos para uma pergunta analitica explicita antes do workflow;
- novas consultas continuam passando pelo grafo, validadores e executor.

## Alternativas consideradas

- Misturar visualizacao diretamente no SQL generator: aumenta acoplamento e risco de regressao.
- Tratar todo follow-up como pergunta nova sem contexto: simples, mas ruim para UX.
- Usar memoria conversacional livre no prompt: flexivel, mas pouco auditavel.

## Consequencias

- O cache de sessao deve armazenar pergunta canonica, SQL, resultado e metadata.
- Follow-ups resolvidos devem registrar `conversation_followup` na metadata.
- Pedidos de grafico sem resultado anterior devem responder com falta de contexto, sem inventar dados.

## Impacto em testes e avaliacao

- Testes devem cobrir `E em 2022?`, `Agora por sexo` e `Faca um grafico`.
- Benchmarks futuros podem medir follow-up como dominio separado.
- A UI deve manter SQL e graficos como detalhes/acoes, sem poluir a resposta curta.
