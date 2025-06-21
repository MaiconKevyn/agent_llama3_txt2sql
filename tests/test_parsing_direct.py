#!/usr/bin/env python3
"""
Direct test of the parsing logic
"""

import sys
import os
import re

# Add parent directory and src to path
parent_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.append(parent_dir)
sys.path.append(os.path.join(parent_dir, 'src'))

from src.application.services.query_processing_service import ComprehensiveQueryProcessingService

# Simulate the actual agent response format
test_response = """
Action: sql_db_query
Action Input: SELECT CIDADE_RESIDENCIA_PACIENTE, COUNT(*) as total FROM sus_data WHERE MORTE = 1 AND SEXO = 1 AND IDADE < 30 GROUP BY CIDADE_RESIDENCIA_PACIENTE ORDER BY total DESC LIMIT 5
Observation: [('Uruguaiana', 20), ('Ijuí', 18), ('Passo Fundo', 16), ('Porto Alegre', 15), ('Santa Maria', 14)]
Final Answer:

The top 5 cities with the most men under 30 who died are Uruguaiana, Ijuí, Passo Fundo, Porto Alegre, and Santa Maria.
"""

print("🧪 Direct Test of Parsing Logic")
print("=" * 50)

# Create a mock service to test the parsing method
class MockQueryService:
    def _parse_agent_results(self, response: str):
        """Parse results from agent response - EXACT COPY from the real service"""
        # Look for the SQL query result pattern [(number,)]
        sql_result_pattern = r'\\[\\((\\d+),\\)\\]'
        sql_match = re.search(sql_result_pattern, response)
        if sql_match:
            result_value = int(sql_match.group(1))
            return [{"result": result_value}], result_value
        
        # Look for Final Answer in the response (with or without colon)
        if "Final Answer:" in response:
            # Extract the final answer part
            final_answer_start = response.find("Final Answer:")
            if final_answer_start != -1:
                final_answer_part = response[final_answer_start + len("Final Answer:"):].strip()
                
                # Check for patterns like "top 5 cities...are City1, City2, City3, City4, and City5"
                # This handles the actual format returned by LangChain
                if "top" in final_answer_part.lower() and "cities" in final_answer_part.lower():
                    # Look for city names in the text
                    cities_pattern = r'are ([^.]+)\\.'  # Extract text after "are" and before "."
                    cities_match = re.search(cities_pattern, final_answer_part)
                    
                    if cities_match:
                        cities_text = cities_match.group(1)
                        # Split by commas and "and" to get individual cities
                        cities = re.split(r',\\s*(?:and\\s+)?', cities_text)
                        cities = [city.strip() for city in cities if city.strip()]
                        
                        # Now extract the actual counts from the agent response
                        # Look for the SQL result pattern in the full response (corrected pattern)
                        sql_result_pattern = r'\\[(\\([^)]+\\)(?:,\\s*\\([^)]+\\))*)\\]'
                        sql_match = re.search(sql_result_pattern, response)
                        
                        if sql_match and cities:
                            # Parse the SQL results
                            sql_results_text = sql_match.group(1)
                            # Pattern like ('Uruguaiana', 20), ('Ijuí', 18), etc.
                            city_count_pattern = r"\\('([^']+)',\\s*(\\d+)\\)"
                            city_count_matches = re.findall(city_count_pattern, sql_results_text)
                            
                            if city_count_matches:
                                structured_results = []
                                for rank, (city, count) in enumerate(city_count_matches, 1):
                                    structured_results.append({
                                        "rank": rank,
                                        "city": city.strip(),
                                        "count": int(count),
                                        "full_text": f"{rank}. {city.strip()} - {count}"
                                    })
                                
                                # Add the complete final answer text for conversational LLM
                                structured_results.append({
                                    "final_answer_text": final_answer_part,
                                    "response_type": "complex_query",
                                    "total_results": len(city_count_matches),
                                    "sql_results": city_count_matches
                                })
                                
                                return structured_results, len(city_count_matches)
                
                # Simple single number result
                numbers = re.findall(r'\\d+', final_answer_part)
                if numbers:
                    result_value = int(numbers[-1])
                    # Include the final answer text for conversational LLM
                    return [
                        {"result": result_value},
                        {"final_answer_text": final_answer_part, "response_type": "simple_query"}
                    ], result_value
        
        # Fallback: return complete response text for conversational LLM to interpret
        return [
            {"final_answer_text": response.strip(), "response_type": "fallback_query"}
        ], 0

# Test the parsing logic
mock_service = MockQueryService()
results, row_count = mock_service._parse_agent_results(test_response)

print(f"📊 Parsing Results:")
print(f"   • Row Count: {row_count}")
print(f"   • Results Count: {len(results)}")

for i, result in enumerate(results):
    print(f"   • Result {i+1}: {list(result.keys())}")
    for key, value in result.items():
        if key == "final_answer_text":
            print(f"     - {key}: {str(value)[:100]}...")
        else:
            print(f"     - {key}: {value}")

print("\n🎯 Expected vs Actual:")
print("   Expected: Complex query with 5 cities")
print(f"   Actual: {'Complex query detected!' if any('response_type' in r and r['response_type'] == 'complex_query' for r in results) else 'Simple query detected'}")