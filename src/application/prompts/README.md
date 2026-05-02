# Prompt Catalogs

Este diretório concentra prompts versionados e catálogos de variantes usados pelo agente.

Estrutura atual:

- `table_selection/`
  - `variants.yml`: variantes de description, prompt e presets nomeados
  - `catalog.py`: loader e renderização do catálogo
- `schema_context/`
  - reservado para o próximo catálogo versionado de contexto de schema

Convenção:

- `config/` continua para configuração operacional do sistema
- `prompts/` guarda assets versionados de prompting e presets experimentais
