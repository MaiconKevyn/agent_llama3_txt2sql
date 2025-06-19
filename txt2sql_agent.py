import sqlite3
from langchain_community.llms import Ollama
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain.agents.agent_types import AgentType
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory
from langchain.chains import LLMChain
import os

class Text2SQLAgent:
    def __init__(self, db_path="sus_database.db", model_name="llama3"):
        """
        Initialize the Text2SQL agent
        
        Args:
            db_path (str): Path to SQLite database
            model_name (str): Ollama model name (llama3 or mistral)
        """
        self.db_path = db_path
        self.model_name = model_name
        
        # Initialize Ollama LLM
        self.llm = Ollama(model=model_name, temperature=0)
        
        # Initialize database connection
        self.db = SQLDatabase.from_uri(f"sqlite:///{db_path}")
        
        # Create SQL toolkit
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)
        
        # Create SQL agent
        self.agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            handle_parsing_errors=True
        )
        
        # Database schema context
        self.schema_context = self._get_schema_context()
    
    def _get_schema_context(self):
        """Get database schema information for context"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get table info
            cursor.execute("PRAGMA table_info(sus_data)")
            columns = cursor.fetchall()
            
            # Get sample data
            cursor.execute("SELECT * FROM sus_data LIMIT 3")
            sample_data = cursor.fetchall()
            
            conn.close()
            
            schema_info = """
Database Schema - SUS Healthcare Data:
Table: sus_data

IMPORTANT: For city-based queries, use CIDADE_RESIDENCIA_PACIENTE column (contains city names like "Porto Alegre", "São Paulo", etc.)

Columns:
- DIAG_PRINC: Principal diagnosis code (ICD-10)
- MUNIC_RES: Municipality of residence code (numeric code, NOT city name)
- MUNIC_MOV: Municipality of hospitalization code (numeric code)
- PROC_REA: Medical procedure code
- IDADE: Patient age
- SEXO: Patient sex (1=Male, 3=Female)
- CID_MORTE: Death cause code
- MORTE: Death indicator (0=No, 1=Yes) - USE THIS FOR DEATH QUERIES
- CNES: Healthcare facility code
- VAL_TOT: Total cost value
- UTI_MES_TO: ICU days total
- DT_INTER: Admission date (YYYYMMDD)
- DT_SAIDA: Discharge date (YYYYMMDD)
- total_ocorrencias: Total occurrences
- UF_RESIDENCIA_PACIENTE: State of residence (text)
- CIDADE_RESIDENCIA_PACIENTE: City of residence (text) - USE THIS FOR CITY NAMES
- LATI_CIDADE_RES: Latitude of residence city
- LONG_CIDADE_RES: Longitude of residence city

QUERY EXAMPLES:
- Deaths in Porto Alegre: SELECT COUNT(*) FROM sus_data WHERE CIDADE_RESIDENCIA_PACIENTE = 'Porto Alegre' AND MORTE = 1
- Patients from a city: SELECT COUNT(*) FROM sus_data WHERE CIDADE_RESIDENCIA_PACIENTE = 'city_name'

Available cities include: Porto Alegre, Santa Maria, Uruguaiana, Pelotas, Caxias do Sul, etc.

This is Brazilian healthcare system (SUS) data with patient hospitalizations.
"""
            return schema_info
            
        except Exception as e:
            return f"Error getting schema: {str(e)}"
    
    def query(self, question):
        """
        Process natural language question and return SQL result
        
        Args:
            question (str): Natural language question
            
        Returns:
            str: Agent response with SQL query and results
        """
        try:
            # Add schema context to the question
            enhanced_question = f"""
{self.schema_context}

Question: {question}

Please write and execute a SQL query to answer this question. 
Be careful with column names and data types.
"""
            
            response = self.agent.run(enhanced_question)
            return response
            
        except Exception as e:
            return f"Error processing query: {str(e)}"
    
    def get_schema(self):
        """Return database schema information"""
        return self.schema_context

def main():
    """Main interface for the Text2SQL agent"""
    
    print("=== Text2SQL Agent for SUS Healthcare Data ===")
    print("Available models: llama3, mistral")
    
    # Choose model
    model_choice = input("Choose model (llama3/mistral) [llama3]: ").strip().lower()
    if not model_choice:
        model_choice = "llama3"
    
    try:
        # Initialize agent
        print(f"\nInitializing agent with {model_choice}...")
        agent = Text2SQLAgent(model_name=model_choice)
        
        print("\nAgent ready! You can ask questions about the healthcare data.")
        print("Type 'schema' to see database structure, 'quit' to exit.")
        print("\nExample questions:")
        print("- How many patients are there?")
        print("- What is the average age of patients?")
        print("- How many deaths occurred?")
        print("- What are the most common diagnoses?")
        print("- What is the total cost by state?")
        
        while True:
            question = input("\nYour question: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                break
            elif question.lower() == 'schema':
                print(agent.get_schema())
            elif question:
                print("\nProcessing your question...")
                response = agent.query(question)
                print(f"\nResponse:\n{response}")
            
        print("Goodbye!")
        
    except Exception as e:
        print(f"Error initializing agent: {str(e)}")
        print("Make sure Ollama is running and the model is installed.")

if __name__ == "__main__":
    main()