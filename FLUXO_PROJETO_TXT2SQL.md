# 🔄 Fluxo Completo do Projeto TXT2SQL

Este documento descreve o fluxo completo de processamento desde quando uma pergunta do usuário entra no sistema até a resposta conversacional final.

## 📊 Diagrama de Fluxo Principal

```mermaid
graph TD
    A[👤 Usuário faz pergunta] --> B{🌐 Ponto de Entrada}
    B -->|Flask App :5000| C[🔧 Text2SQL Orchestrator]
    B -->|FastAPI :8000| C
    B -->|Simple API :5002| C
    
    C --> D[✅ Validação e Sanitização]
    D --> E[📝 Criação QueryRequest]
    E --> F[🔍 Query Processing Service]
    
    F --> G[📋 Schema Introspection Service]
    G --> H[📚 Contexto do Banco SUS]
    H --> I[✨ Prompt Melhorado + Regras SUS]
    
    I --> J[🤖 LangChain SQL Agent<br/>LLM Layer 1]
    J --> K[🗃️ Database Service]
    K --> L[⚡ Execução SQL]
    L --> M[📊 Resultados Brutos]
    
    M --> N[🔧 Correção Case Sensitivity]
    N --> O[📋 Parse de Resultados]
    O --> P[📦 QueryResult Object]
    
    P --> Q{🎭 Resposta Conversacional?}
    
    Q -->|Não| R[📝 Resposta Básica]
    Q -->|Sim| S[💬 Conversational Response Service]
    
    S --> T[🏥 SUS Prompt Template Service]
    T --> U{📊 Tipo de Análise}
    
    U -->|Estatística| V[📈 Template Estatístico]
    U -->|Comparativa| W[⚖️ Template Comparativo]
    U -->|Geográfica| X[🗺️ Template Geográfico]
    U -->|Básica| Y[💬 Template Básico]
    
    V --> Z[🎯 Prompt Especializado SUS]
    W --> Z
    X --> Z
    Y --> Z
    
    Z --> AA[🤖 Conversational LLM<br/>LLM Layer 2]
    AA --> BB[💬 Resposta Amigável em PT-BR]
    BB --> CC[✨ Metadados e Sugestões]
    
    R --> DD[📤 Resposta Final JSON]
    CC --> DD
    DD --> EE[👤 Usuário recebe resposta]
    
    style A fill:#e1f5fe
    style J fill:#fff3e0
    style AA fill:#f3e5f5
    style DD fill:#e8f5e8
    style EE fill:#e1f5fe
```

## 🏗️ Arquitetura de Serviços

```mermaid
graph LR
    subgraph "🌐 Pontos de Entrada"
        A[Flask App]
        B[FastAPI]
        C[Simple API]
    end
    
    subgraph "🎯 Orchestração"
        D[Text2SQL Orchestrator]
    end
    
    subgraph "🔍 Processamento de Query"
        E[Query Processing Service]
        F[Schema Introspection Service]
        G[Input Validator]
    end
    
    subgraph "🤖 Comunicação LLM"
        H[LLM Communication Service]
        I[Conversational LLM Service]
    end
    
    subgraph "💬 Resposta Conversacional"
        J[Conversational Response Service]
        K[SUS Prompt Template Service]
    end
    
    subgraph "🗃️ Dados"
        L[Database Connection Service]
        M[SQLite SUS Database]
    end
    
    subgraph "⚙️ Infraestrutura"
        N[Error Handling Service]
        O[Dependency Container]
    end
    
    A --> D
    B --> D
    C --> D
    D --> E
    E --> F
    E --> H
    E --> L
    D --> J
    J --> I
    J --> K
    L --> M
    O --> E
    O --> H
    O --> I
    O --> J
    O --> L
    O --> N
```

## 🔄 Fluxo Detalhado de Processamento

```mermaid
sequenceDiagram
    participant U as 👤 Usuário
    participant API as 🌐 API Endpoint
    participant O as 🎯 Orchestrator
    participant QPS as 🔍 Query Processing
    participant SIS as 📋 Schema Service
    participant LLM1 as 🤖 LangChain Agent
    participant DB as 🗃️ Database
    participant CRS as 💬 Conversational Service
    participant SUS as 🏥 SUS Templates
    participant LLM2 as 🤖 Conversational LLM
    
    U->>API: POST /query {"question": "Quantos pacientes?"}
    API->>O: process_conversational_query(question)
    
    O->>O: validate_input(question)
    O->>QPS: process_natural_language_query(request)
    
    QPS->>SIS: get_schema_context()
    SIS-->>QPS: schema + SUS context
    
    QPS->>QPS: create_enhanced_prompt()
    Note over QPS: Adiciona regras SUS:<br/>SEXO=1 (masculino)<br/>CIDADE_RESIDENCIA_PACIENTE formato
    
    QPS->>LLM1: agent.run(enhanced_prompt)
    LLM1->>DB: execute_sql_query()
    DB-->>LLM1: sql_results
    LLM1-->>QPS: agent_response + results
    
    QPS->>QPS: fix_case_sensitivity_issues()
    QPS->>QPS: parse_agent_results()
    QPS-->>O: QueryResult{sql, results, success, time}
    
    O->>CRS: generate_response(query, sql, results)
    CRS->>SUS: get_prompt_template(query_type)
    SUS-->>CRS: specialized_template
    
    CRS->>LLM2: generate_conversational_response()
    Note over LLM2: Temperatura 0.7<br/>Especialista SUS<br/>Português brasileiro
    
    LLM2-->>CRS: "**Resumo Direto:**<br/>Existem 56 pacientes<br/>**Dados Detalhados:**<br/>..."
    
    CRS->>CRS: enhance_with_metadata()
    CRS-->>O: FormattedResponse{content, metadata, suggestions}
    
    O-->>API: {"success": true, "response": "...", "metadata": {...}}
    API-->>U: JSON Response
```

## 📋 Transformações de Dados

```mermaid
flowchart TD
    A["🔤 Pergunta Natural<br/>'Quantos homens?'"] --> B["📝 Query Sanitizada<br/>'Quantos homens?'"]
    
    B --> C["🔍 Prompt Melhorado<br/>Schema + Regras SUS<br/>SEXO = 1 significa masculino"]
    
    C --> D["💾 SQL Query<br/>SELECT COUNT(*) FROM pacientes<br/>WHERE SEXO = 1"]
    
    D --> E["📊 Resultados SQL<br/>[{'count': 28}]"]
    
    E --> F["🎯 Prompt Conversacional<br/>Contexto SUS + Resultados<br/>Template especializado"]
    
    F --> G["💬 Resposta Amigável<br/>**Resumo Direto:**<br/>Existem 28 pacientes homens<br/>**Dados Detalhados:**<br/>Este número representa..."]
    
    G --> H["📦 Resposta Final<br/>{success: true, response: '...', metadata: {...}}"]
    
    style A fill:#e3f2fd
    style D fill:#fff3e0
    style G fill:#f3e5f5
    style H fill:#e8f5e8
```

## 🏥 Especialização para Domínio SUS

```mermaid
mindmap
  root((🏥 SUS Domain))
    🔍 Schema Context
      Tabelas especializadas
      Campos de saúde
      Relacionamentos
    📋 Regras de Negócio
      SEXO: 1=Masculino, 3=Feminino
      MORTE: 0=Vivo, 1=Óbito
      Cidades com capitalização
    🎯 Templates de Prompt
      Análise Estatística
      Análise Comparativa
      Análise Geográfica
      Análise de Tendências
    💬 Respostas Contextualizadas
      Terminologia médica PT-BR
      Explicações para gestores
      Sugestões de análises
      Insights de saúde pública
```

## ⚡ Principais Componentes

### 🎯 **Text2SQLOrchestrator**
- **Função**: Coordenador central do fluxo
- **Responsabilidades**: Validação, orquestração de serviços, formatação de resposta
- **Método Principal**: `process_conversational_query()`

### 🔍 **QueryProcessingService** 
- **Função**: Conversão de linguagem natural para SQL
- **Tecnologia**: LangChain SQL Agent + Ollama
- **Especialização**: Regras específicas para dados SUS brasileiros

### 💬 **ConversationalResponseService**
- **Função**: Geração de respostas amigáveis
- **Características**: Memória de contexto, sugestões inteligentes
- **Integração**: SUS Prompt Templates + Conversational LLM

### 🏥 **SUSPromptTemplateService**
- **Função**: Templates especializados para análises de saúde
- **Tipos**: Estatística, Comparativa, Geográfica, Tendências
- **Base de Conhecimento**: Terminologia SUS, indicadores de saúde

### 🗃️ **DatabaseConnectionService**
- **Função**: Gerenciamento de conexões SQLite
- **Dupla Interface**: LangChain SQLDatabase + conexão raw
- **Dados**: Base SUS com informações de pacientes

## 🎯 Resultado Final

O sistema produz respostas conversacionais estruturadas em português brasileiro:

```json
{
  "success": true,
  "question": "Quantos pacientes são homens?",
  "response": "**Resumo Direto:**\nExistem 28 pacientes do sexo masculino cadastrados.\n\n**Dados Detalhados:**\nEste número representa uma parcela significativa dos pacientes atendidos pelo SUS, fornecendo informações importantes para o planejamento de políticas de saúde específicas para a população masculina.",
  "execution_time": 12.34,
  "metadata": {
    "conversational_response": true,
    "response_type": "statistical_analysis",
    "confidence_score": 0.9,
    "suggestions": [
      "Gostaria de ver a distribuição por faixa etária?",
      "Posso comparar com dados de outras regiões",
      "Quer analisar tendências temporais destes dados?"
    ]
  },
  "timestamp": "2025-06-20T11:30:00.000Z"
}
```

## 🚀 Benefícios da Arquitetura

- **🔧 Modularidade**: Cada serviço tem responsabilidade única
- **🧪 Testabilidade**: Componentes podem ser testados isoladamente  
- **⚙️ Configurabilidade**: Diferentes implementações via factories
- **🌐 Escalabilidade**: Serviços podem ser distribuídos
- **🏥 Especialização**: Otimizado para domínio SUS brasileiro
- **💬 UX Amigável**: Respostas naturais em português brasileiro