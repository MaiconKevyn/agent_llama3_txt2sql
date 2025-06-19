# TXT2SQL Claude - Clean Architecture

Sistema de consultas em linguagem natural para dados de saúde brasileiros (SUS) usando arquitetura limpa e princípios SOLID.

## 🚀 Como Usar

### Instalação
```bash
pip install -r requirements.txt
```

### Configurar Banco de Dados
```bash
python database_setup.py
```

### Executar o Agente

#### Interface Interativa (Padrão)
```bash
python txt2sql_agent_clean.py
```

#### Interface Básica
```bash
python txt2sql_agent_clean.py --basic
```

#### Consulta Única
```bash
python txt2sql_agent_clean.py --query "Quantas mortes em Porto Alegre?"
```

#### Verificação de Saúde
```bash
python txt2sql_agent_clean.py --health-check
```

#### Informações da Arquitetura
```bash
python txt2sql_agent_clean.py --version
```

## 🏗️ Arquitetura

### Estrutura do Projeto
```
├── src/application/
│   ├── services/           # 6 serviços especializados (SRP)
│   ├── container/          # Injeção de dependências
│   └── orchestrator/       # Coordenação de serviços
├── data/                   # Dados SUS
├── database_setup.py       # Configuração do banco
├── txt2sql_agent_clean.py  # Ponto de entrada principal
└── sus_database.db         # Banco SQLite
```

### Serviços Implementados

1. **DatabaseConnectionService** - Gerenciamento de conexões
2. **LLMCommunicationService** - Comunicação com LLM
3. **SchemaIntrospectionService** - Análise de schema
4. **UserInterfaceService** - Interface com usuário
5. **ErrorHandlingService** - Tratamento de erros
6. **QueryProcessingService** - Processamento de consultas

### Princípios SOLID

✅ **Single Responsibility** - Cada serviço tem uma responsabilidade  
✅ **Open/Closed** - Extensível sem modificações  
✅ **Liskov Substitution** - Implementações substituíveis  
✅ **Interface Segregation** - Interfaces específicas  
✅ **Dependency Inversion** - Dependências injetadas  

## 📋 Requisitos

- Python 3.8+
- Ollama rodando localmente
- Modelo LLM instalado (llama3, mistral)

### Instalar Ollama
```bash
# Instalar Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Iniciar serviço
ollama serve

# Instalar modelo
ollama pull llama3
```

## 💡 Exemplos de Consultas

- "Quantos pacientes existem?"
- "Qual a idade média dos pacientes?"
- "Quantas mortes ocorreram em Porto Alegre?"
- "Quais são os diagnósticos mais comuns?"
- "Qual o custo total por estado?"

## 📊 Dados

O sistema utiliza dados do SUS (Sistema Único de Saúde) brasileiro com:
- 24.485 registros de pacientes
- Informações de diagnósticos (CID-10)
- Dados geográficos (cidades, estados)
- Custos de procedimentos
- Indicadores de mortalidade

## 🔧 Solução de Problemas

### Verificar Status do Sistema
```bash
python txt2sql_agent_clean.py --health-check
```

### Problemas Comuns

1. **Ollama não conecta**: Verificar se `ollama serve` está rodando
2. **Modelo não encontrado**: Executar `ollama pull llama3`
3. **Banco não existe**: Executar `python database_setup.py`

## 📚 Documentação Técnica

Para detalhes completos da arquitetura, consulte:
- `CLEAN_ARCHITECTURE_SUMMARY.md` - Documentação técnica completa

## 🎯 Sobre a Arquitetura

Este projeto demonstra a transformação de um sistema monolítico em uma arquitetura limpa que segue os princípios SOLID. Cada componente tem responsabilidades bem definidas, tornando o sistema:

- **Testável** - Cada serviço pode ser testado independentemente
- **Manutenível** - Mudanças isoladas não afetam outros componentes  
- **Extensível** - Novos recursos podem ser adicionados facilmente
- **Profissional** - Segue padrões enterprise de desenvolvimento