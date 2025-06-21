#!/usr/bin/env python3
"""
Debug the regex pattern matching for complex queries
"""

import re

# Simulate the actual agent response from the test
agent_response = """
Action: sql_db_query
Action Input: SELECT CIDADE_RESIDENCIA_PACIENTE, COUNT(*) as total FROM sus_data WHERE MORTE = 1 AND SEXO = 1 AND IDADE < 30 GROUP BY CIDADE_RESIDENCIA_PACIENTE ORDER BY total DESC LIMIT 5
[('Uruguaiana', 20), ('Ijuí', 18), ('Passo Fundo', 16), ('Porto Alegre', 15), ('Santa Maria', 14)]

Final Answer:

The top 5 cities with the most men under 30 who died are Uruguaiana, Ijuí, Passo Fundo, Porto Alegre, and Santa Maria.
"""

print("🔍 Testing Regex Patterns on Actual Agent Response")
print("=" * 60)

# Test the current SQL result pattern
sql_result_pattern = r'\[(\([^)]+\)(?:,\s*\([^)]+\))*)\]'
sql_match = re.search(sql_result_pattern, agent_response)
print(f"1. SQL Results Pattern: {sql_result_pattern}")
print(f"   Match: {sql_match.group(1) if sql_match else 'NO MATCH'}")

if sql_match:
    # Test city-count extraction from the SQL results
    sql_results_text = sql_match.group(1)
    print(f"   SQL Results Text: {sql_results_text}")
    
    # Pattern to extract individual city-count pairs
    city_count_pattern = r"\('([^']+)',\s*(\d+)\)"
    city_count_matches = re.findall(city_count_pattern, sql_results_text)
    print(f"   City-Count Matches: {city_count_matches}")

print("\n" + "-" * 60)

# Test Final Answer detection
final_answer_pattern = r"Final Answer:\s*(.*)"
final_match = re.search(final_answer_pattern, agent_response, re.DOTALL)
print(f"2. Final Answer Pattern: {final_answer_pattern}")
print(f"   Match: {final_match.group(1)[:100] if final_match else 'NO MATCH'}...")

if final_match:
    final_answer_text = final_match.group(1).strip()
    print(f"   Final Answer Text: {final_answer_text}")
    
    # Check if it mentions "top" and "cities"
    if "top" in final_answer_text.lower() and "cities" in final_answer_text.lower():
        print("   ✅ Detected as complex query (mentions 'top' and 'cities')")
        
        # Extract cities from final answer
        cities_pattern = r'are ([^.]+)\.'
        cities_match = re.search(cities_pattern, final_answer_text)
        if cities_match:
            cities_text = cities_match.group(1)
            print(f"   Cities Text: {cities_text}")
            
            # Split cities by comma and "and"
            cities = re.split(r',\s*(?:and\s+)?', cities_text)
            cities = [city.strip() for city in cities if city.strip()]
            print(f"   Extracted Cities: {cities}")
    else:
        print("   ❌ Not detected as complex query")

print("\n" + "=" * 60)
print("🎯 Summary: The agent response contains all the data we need!")
print("   • SQL Results with counts: ✅")
print("   • Final Answer with city names: ✅")
print("   • Pattern matching: Need to fix the regex")