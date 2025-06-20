#!/usr/bin/env python3
"""
CLI tool to test the TXT2SQL API
"""
import requests
import json
import sys
from datetime import datetime

API_URL = "http://localhost:8000"

def test_health():
    """Test API health"""
    try:
        response = requests.get(f"{API_URL}/health")
        print("🔍 Health Check:")
        print(json.dumps(response.json(), indent=2))
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def send_query(question: str):
    """Send a query to the API"""
    try:
        payload = {"question": question}
        response = requests.post(
            f"{API_URL}/query",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        result = response.json()
        
        print(f"\n🤖 Query: {question}")
        print("=" * 50)
        
        if result.get("success"):
            print(f"✅ Status: Success")
            print(f"⏱️  Execution Time: {result.get('execution_time', 0):.2f}s")
            print(f"📊 Row Count: {result.get('row_count', 0)}")
            
            if result.get("results"):
                print(f"📋 Results:")
                for i, row in enumerate(result["results"][:5], 1):
                    print(f"  {i}. {row}")
                
                if result.get("row_count", 0) > 5:
                    print(f"  ... and {result.get('row_count') - 5} more")
            
            if result.get("sql_query"):
                print(f"\n🔍 Generated SQL:")
                print(f"  {result['sql_query']}")
        else:
            print(f"❌ Status: Failed")
            print(f"💥 Error: {result.get('error_message', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

def get_schema():
    """Get database schema"""
    try:
        response = requests.get(f"{API_URL}/schema")
        result = response.json()
        print("\n📊 Database Schema:")
        print("=" * 50)
        print(result.get("schema", "No schema available"))
    except Exception as e:
        print(f"❌ Schema request failed: {e}")

def interactive_mode():
    """Interactive CLI mode"""
    print("🗃️  TXT2SQL CLI Test Tool")
    print("Type 'health' to check API status")
    print("Type 'schema' to see database schema")
    print("Type 'quit' to exit")
    print("Or ask any question about the database")
    print("-" * 50)
    
    while True:
        try:
            question = input("\n💬 Your question: ").strip()
            
            if not question:
                continue
            elif question.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye!")
                break
            elif question.lower() == 'health':
                test_health()
            elif question.lower() == 'schema':
                get_schema()
            else:
                send_query(question)
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

def main():
    """Main function"""
    if len(sys.argv) > 1:
        # Command line mode
        question = " ".join(sys.argv[1:])
        if question.lower() == 'health':
            test_health()
        elif question.lower() == 'schema':
            get_schema()
        else:
            send_query(question)
    else:
        # Interactive mode
        interactive_mode()

if __name__ == "__main__":
    main()