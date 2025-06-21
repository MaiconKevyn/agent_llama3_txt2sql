#!/usr/bin/env python3
"""
Test script for conversational LLM implementation.
"""

import sys
import os

# Add parent directory and src to path
parent_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.append(parent_dir)
sys.path.append(os.path.join(parent_dir, 'src'))

from src.application.services.conversational_llm_service import ConversationalLLMService
from src.application.services.conversational_response_service import ConversationalResponseService
from src.application.services.sus_prompt_template_service import SUSPromptTemplateService, PromptType

def test_conversational_service():
    """Test the conversational service components."""
    
    print("🧪 Testing Conversational LLM Implementation")
    print("=" * 50)
    
    # Test 1: ConversationalLLMService initialization
    print("\n1️⃣ Testing ConversationalLLMService...")
    try:
        conv_llm = ConversationalLLMService()
        print(f"✅ ConversationalLLMService initialized")
        print(f"📋 Model: {conv_llm.config.model_name}")
        print(f"🌡️ Temperature: {conv_llm.config.temperature}")
        print(f"🔗 Available: {conv_llm.is_available()}")
    except Exception as e:
        print(f"❌ ConversationalLLMService failed: {e}")
        return False
    
    # Test 2: SUSPromptTemplateService
    print("\n2️⃣ Testing SUSPromptTemplateService...")
    try:
        prompt_service = SUSPromptTemplateService()
        templates = prompt_service.get_available_templates()
        print(f"✅ SUSPromptTemplateService initialized")
        print(f"📝 Available templates: {len(templates)}")
        
        # Test prompt type detection
        test_query = "Quantos pacientes existem por estado?"
        prompt_type = prompt_service.determine_prompt_type(test_query)
        print(f"🔍 Query '{test_query}' detected as: {prompt_type.value}")
        
    except Exception as e:
        print(f"❌ SUSPromptTemplateService failed: {e}")
        return False
    
    # Test 3: ConversationalResponseService
    print("\n3️⃣ Testing ConversationalResponseService...")
    try:
        conv_response = ConversationalResponseService()
        print(f"✅ ConversationalResponseService initialized")
        print(f"🤖 LLM Available: {conv_response.is_conversational_llm_available()}")
        
        # Test status
        status = conv_response.get_service_status()
        print(f"📊 Service Status:")
        for key, value in status.items():
            print(f"   • {key}: {value}")
            
    except Exception as e:
        print(f"❌ ConversationalResponseService failed: {e}")
        return False
    
    # Test 4: End-to-end conversational response (if LLM is available)
    print("\n4️⃣ Testing End-to-End Conversational Response...")
    try:
        if conv_response.is_conversational_llm_available():
            print("🚀 Testing conversational response generation...")
            
            # Simulate query results
            test_query = "Quantos pacientes temos no total?"
            test_sql = "SELECT COUNT(*) as total_pacientes FROM pacientes"
            test_results = [{"total_pacientes": 1234}]
            
            response = conv_response.generate_response(
                user_query=test_query,
                sql_query=test_sql,
                sql_results=test_results,
                session_id="test_session"
            )
            
            print(f"✅ Conversational response generated!")
            print(f"📝 Response type: {response.response_type.value}")
            print(f"⏱️ Processing time: {response.processing_time:.2f}s")
            print(f"🎯 Confidence: {response.confidence_score:.2f}")
            print(f"💡 Suggestions: {len(response.suggestions)}")
            print(f"📄 Response preview: {response.message[:200]}...")
            
        else:
            print("⚠️ Conversational LLM not available - skipping end-to-end test")
            print("💡 Make sure Ollama is running with llama3.1:8b-instruct model")
            
    except Exception as e:
        print(f"❌ End-to-end test failed: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("🎉 All conversational tests completed successfully!")
    return True

if __name__ == "__main__":
    success = test_conversational_service()
    sys.exit(0 if success else 1)