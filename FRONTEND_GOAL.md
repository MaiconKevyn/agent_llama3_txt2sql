# FRONTEND GOAL - Professional Desktop UI

## Objetivo

Elevar o frontend em `frontend/` para um nivel profissional de produto, com foco inicial em desktop/PC. A interface deve parecer uma ferramenta de consulta e analise de dados em saude, nao uma landing page promocional.

O resultado esperado e uma experiencia mais clara, confiavel, agradavel aos olhos e facil de manter, preservando a stack atual:

- HTML estatico em `frontend/public/index.html`
- CSS em `frontend/public/styles.css`
- JavaScript vanilla em `frontend/public/app.js`
- Express proxy em `frontend/server.js`

Nao migrar para React/Vite/Next nesta etapa. A melhoria deve acontecer dentro da arquitetura atual.

## Escopo Inicial

Prioridade: desktop a partir de `1024px`.

Fora do escopo imediato:

- Redesign mobile completo
- Mudanca de contrato da API
- Migracao de framework
- Alteracoes no backend do agent
- Novas features complexas de analise que dependam do backend

## Skills e Best Practices a Aplicar

Use estas skills como referencia de implementacao quando estiverem disponiveis no Codex:

- `ui-ux-pro-max`: orientar decisoes de layout, hierarquia visual, cores, tipografia, estados e acessibilidade.
- `web-design-guidelines`: revisar acessibilidade, foco, semantica, formularios, estados de erro e comportamento da interface.
- `design-audit`: fazer auditoria visual antes/depois e transformar achados em ajustes implementaveis.
- `ui-styling`: guiar padronizacao de componentes, tokens, botao, input, modal e tabelas.
- `design-system`: estruturar tokens locais de cor, espacamento, radius, sombra e estados.
- `typography`: melhorar legibilidade, hierarquia textual e consistencia de copy.

Best practices obrigatorias:

- Interface de ferramenta: densa o suficiente para uso repetido, mas sem poluicao visual.
- Chat como foco principal no desktop.
- Sidebar deve ajudar a consulta, nao competir com o chat.
- Usar estados claros: verificando, online, offline, carregando, erro, vazio.
- Evitar dependencias visuais de hover apenas; todos os controles precisam de foco visivel.
- Manter contraste adequado para texto normal e controles.
- Remover CSS duplicado antes de ampliar componentes.
- Evitar cards dentro de cards quando uma separacao por layout ou banda resolve melhor.
- Evitar gradientes decorativos excessivos; usar cor para hierarquia e status.
- Validar visualmente em `1440x900` e `1280x800`.

## Checkpoint 0 - Baseline e Inventario

Objetivo: registrar o estado atual antes de alterar a interface.

Tarefas:

- Capturar screenshot desktop em `1440x900`.
- Capturar screenshot desktop em `1280x800`.
- Verificar console do navegador sem filtrar erros.
- Testar manualmente os fluxos:
  - abrir tela inicial
  - clicar em exemplo de consulta
  - enviar pergunta
  - limpar conversa
  - alternar tema
  - abrir modal de schema
- Registrar problemas visuais encontrados.

Critérios de aceite:

- Existe baseline visual antes das mudancas.
- Os fluxos principais estao documentados como funcionando, falhando ou dependentes do agent.
- Nenhuma alteracao de produto foi feita neste checkpoint.

## Checkpoint 1 - Correcoes Imediatas de Percepcao

Objetivo: remover problemas que fazem a tela parecer quebrada ou amadora.

Tarefas:

- Remover duplicacao da mensagem de boas-vindas.
- Trocar status inicial de `Online` para `Verificando...`.
- Atualizar status para `Online` somente apos health real do agent.
- Usar status `Agent offline` com copy clara quando o agent nao responder.
- Remover ou integrar corretamente o loading overlay que hoje nao participa do fluxo principal.
- Corrigir o favicon ausente ou adicionar fallback para evitar 404 visual/logico.
- Revisar copy inicial para explicar melhor o que o usuario pode perguntar.

Critérios de aceite:

- A primeira tela mostra apenas uma mensagem inicial.
- O usuario nao ve `Online` antes da verificacao.
- Agent offline aparece como estado esperado, nao como falha confusa.
- Console nao mostra 404 de favicon.
- A tela inicial parece intencional mesmo com o agent offline.

## Checkpoint 2 - Arquitetura Visual Desktop

Objetivo: reorganizar a tela em uma ferramenta de trabalho clara.

Tarefas:

- Reduzir altura e peso visual do header.
- Manter marca/produto visivel, mas sem ocupar area excessiva.
- Definir layout desktop com zonas claras:
  - header compacto
  - sidebar funcional
  - area principal de chat
- Ajustar largura da sidebar para conteudo de suporte.
- Aumentar o protagonismo do chat e do input.
- Evitar rolagem desnecessaria na primeira dobra em `1440x900`.
- Manter altura do chat estavel e previsivel.

Critérios de aceite:

- Em desktop, o primeiro olhar cai no chat/input.
- Sidebar nao parece uma landing page ou lista promocional.
- Header nao compete com o conteudo.
- A tela fica equilibrada em `1440x900` e `1280x800`.

## Checkpoint 3 - Design System Local

Objetivo: criar consistencia visual e reduzir improviso no CSS.

Tarefas:

- Revisar tokens em `:root`:
  - cores semanticas
  - cores de status
  - backgrounds
  - texto primario/secundario/muted
  - bordas
  - sombras
  - radius
  - espacamentos
- Reduzir gradientes decorativos.
- Padronizar sombras para uma linguagem mais profissional.
- Padronizar radius entre cards, botoes, input, modal e mensagens.
- Criar estados compartilhados para:
  - hover
  - active
  - disabled
  - focus-visible
  - loading
- Organizar `styles.css` por secoes:
  - tokens
  - reset/base
  - layout
  - header
  - sidebar
  - chat
  - input
  - modal
  - schema/table
  - toast/status
  - responsive

Critérios de aceite:

- Componentes usam tokens, nao valores soltos sem motivo.
- A paleta comunica saude/dados/confianca sem exagero visual.
- Sombras e bordas estao consistentes.
- O CSS fica mais facil de revisar e alterar.

## Checkpoint 4 - Sidebar Como Painel de Ajuda

Objetivo: transformar a sidebar em um suporte real para consulta.

Tarefas:

- Reduzir a secao "Sobre o Sistema" ou transforma-la em indicadores compactos.
- Priorizar exemplos de consulta.
- Agrupar exemplos por tipo de tarefa:
  - rankings
  - medias
  - comparacoes
  - filtros demograficos
  - consultas por municipio
- Melhorar textos dos exemplos para serem perguntas completas e naturais.
- Adicionar pequena indicacao do que acontece ao clicar em exemplo.
- Avaliar se clique no exemplo deve:
  - preencher o input, ou
  - preencher e enviar automaticamente.
- Preferir comportamento mais controlavel: preencher input primeiro, enviar so com acao explicita.

Critérios de aceite:

- Usuario entende rapidamente o tipo de pergunta suportada.
- Exemplos estao mais proximos de perguntas reais.
- Clique em exemplo nao surpreende o usuario.
- Sidebar fica escaneavel em menos de 5 segundos.

## Checkpoint 5 - Experiencia do Chat

Objetivo: tornar a conversa confortavel para leitura e uso repetido.

Tarefas:

- Redesenhar bolhas de mensagem com melhor largura, contraste e espacamento.
- Reduzir peso visual dos avatares.
- Diferenciar estados:
  - usuario
  - assistente
  - erro
  - loading
  - aviso de contexto
- Melhorar estado de loading inline:
  - mensagem curta
  - indicador discreto
  - sem bloquear a tela inteira
- Reposicionar tempo de execucao para nao competir com resposta.
- Adicionar acao de copiar resposta quando houver resposta do assistente.
- Preparar area futura para SQL/metadados sem expor por padrao.
- Garantir que conversas longas continuam legiveis.

Critérios de aceite:

- Respostas longas ficam confortaveis de ler.
- Erros sao claros e acionaveis.
- Loading comunica progresso sem parecer travamento.
- Acoes secundarias nao poluem a resposta.

## Checkpoint 6 - Input e Fluxo de Envio

Objetivo: deixar o principal ponto de interacao mais claro e eficiente.

Tarefas:

- Melhorar placeholder para orientar melhor a pergunta.
- Adicionar texto auxiliar discreto com exemplo ou limite.
- Manter `Enter` para enviar e `Shift+Enter` para nova linha.
- Exibir estado disabled com motivo visual claro.
- Evitar que o botao de envio pareca clicavel quando vazio.
- Considerar contador simples se houver limite de 1000 caracteres.
- Ao clicar em exemplo, focar input e posicionar cursor no final.

Critérios de aceite:

- Usuario sabe onde digitar e o que digitar.
- O input fica visualmente central no fluxo.
- Estados de vazio, digitando, enviando e erro sao distintos.
- O comportamento de teclado e previsivel.

## Checkpoint 7 - Modal de Schema

Objetivo: transformar o schema em uma ferramenta util e legivel no desktop.

Tarefas:

- Melhorar header do modal com titulo, descricao curta e acao de fechar clara.
- Separar controles do conteudo.
- Melhorar select de tabela e botao carregar.
- Criar estados de schema:
  - vazio inicial
  - carregando
  - erro
  - tabela carregada
- Consolidar CSS duplicado de:
  - `.schema-table`
  - `.filter-results-count`
  - `.clear-filters-btn`
- Padronizar tabela:
  - cabecalho fixo
  - linhas escaneaveis
  - filtros por coluna
  - contador de registros
  - scroll horizontal controlado
- Evitar inserir HTML nao confiavel quando texto simples for suficiente.

Critérios de aceite:

- Modal abre com estado inicial claro.
- Schema completo ou por tabela fica facil de inspecionar em desktop.
- Regras CSS de tabela nao se contradizem.
- Fechar modal e voltar ao chat e simples.

## Checkpoint 8 - Acessibilidade Desktop

Objetivo: corrigir acessibilidade basica antes de polish visual.

Tarefas:

- Adicionar `aria-label` em botoes icon-only.
- Adicionar `role="dialog"` e `aria-modal="true"` no modal.
- Vincular modal a titulo com `aria-labelledby`.
- Garantir labels para select e textarea.
- Implementar `:focus-visible` consistente para botoes, input, select e modal close.
- Garantir que toast tenha papel apropriado:
  - erro: `role="alert"`
  - mensagem informativa: `status`
- Garantir ordem de tabulacao previsivel.
- Fechar modal com `Escape`.
- Retornar foco ao botao que abriu o modal.
- Respeitar `prefers-reduced-motion`.

Critérios de aceite:

- Interface principal pode ser usada por teclado.
- Foco visivel nao e removido.
- Modal e compreensivel para tecnologias assistivas.
- Animacoes reduzem quando o usuario prefere menos movimento.

## Checkpoint 9 - Limpeza de JavaScript

Objetivo: reduzir comportamento implicito e tornar o fluxo mais confiavel.

Tarefas:

- Remover funcoes nao usadas ou integra-las corretamente.
- Evitar duplicar estado entre HTML inicial e JS.
- Centralizar renderizacao da mensagem inicial no JS ou no HTML, nao ambos.
- Separar funcoes por responsabilidade:
  - estado de sessao
  - historico
  - renderizacao de mensagens
  - API
  - schema
  - tema
  - status
- Evitar `innerHTML` quando `textContent` e suficiente.
- Quando `innerHTML` for necessario, limitar a fontes controladas.
- Melhorar tratamento de erro por tipo:
  - agent offline
  - timeout
  - resposta invalida
  - rate limit

Critérios de aceite:

- Fluxo inicial e deterministico.
- Historico e mensagem inicial nao duplicam.
- Erros ficam mais previsiveis.
- Codigo fica mais facil de testar manualmente.

## Checkpoint 10 - Qualidade Visual Final

Objetivo: aplicar acabamento profissional apos corrigir estrutura e usabilidade.

Tarefas:

- Revisar espacamentos verticais e horizontais.
- Ajustar alinhamento de icones e textos.
- Melhorar hierarquia de titulos.
- Rever tons de verde/azul para evitar saturacao excessiva.
- Ajustar tema escuro para contraste e consistencia.
- Remover aparencia de "template generico".
- Verificar que nenhum texto fica apagado demais.
- Revisar microcopy em PT-BR.

Critérios de aceite:

- Interface parece produto profissional e nao prototipo.
- Tema claro e tema escuro sao coerentes.
- Elementos principais estao alinhados.
- A interface transmite confianca, clareza e foco em dados.

## Checkpoint 11 - Validacao Desktop

Objetivo: validar que a melhoria realmente funcionou.

Tarefas:

- Capturar screenshot final em `1440x900`.
- Capturar screenshot final em `1280x800`.
- Comparar antes/depois.
- Testar manualmente:
  - abrir tela
  - checar status
  - selecionar exemplo
  - enviar pergunta
  - visualizar erro se agent offline
  - limpar conversa
  - alternar tema
  - abrir schema
  - carregar schema
  - fechar modal
- Verificar console sem erros novos.
- Verificar que o servidor frontend sobe com `HOST=127.0.0.1 PORT=3050 npm start`.

Critérios de aceite:

- Screenshots finais mostram ganho claro de organizacao e polish.
- Nenhum fluxo principal ficou pior.
- Interface renderiza bem mesmo se o agent estiver offline.
- Mudancas ficam restritas ao frontend salvo necessidade explicita.

## Ordem Recomendada de Implementacao

1. Checkpoint 0 - Baseline e Inventario
2. Checkpoint 1 - Correcoes Imediatas de Percepcao
3. Checkpoint 2 - Arquitetura Visual Desktop
4. Checkpoint 3 - Design System Local
5. Checkpoint 5 - Experiencia do Chat
6. Checkpoint 6 - Input e Fluxo de Envio
7. Checkpoint 4 - Sidebar Como Painel de Ajuda
8. Checkpoint 7 - Modal de Schema
9. Checkpoint 8 - Acessibilidade Desktop
10. Checkpoint 9 - Limpeza de JavaScript
11. Checkpoint 10 - Qualidade Visual Final
12. Checkpoint 11 - Validacao Desktop

## Definition of Done

O trabalho sera considerado concluido quando:

- A interface desktop estiver visualmente mais profissional em `1440x900` e `1280x800`.
- A tela inicial nao tiver duplicacao, status enganoso ou elementos quebrados.
- O usuario conseguir entender rapidamente o que pode perguntar.
- O chat for o centro da experiencia.
- Sidebar, input, mensagens e schema tiverem hierarquia clara.
- Acessibilidade basica por teclado estiver coberta.
- CSS duplicado e regras conflitantes forem reduzidos.
- O frontend continuar funcionando sem exigir mudancas no backend.
- A revisao final incluir screenshots e resumo objetivo do antes/depois.
