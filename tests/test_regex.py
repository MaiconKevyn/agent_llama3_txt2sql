#!/usr/bin/env python3
"""
Test the regex pattern matching
"""

import re

# The actual agent response from the debug
test_response = """
Action: sql_db_query
Action Input: SELECT COUNT(*) FROM sus_data WHERE CIDADE_RESIDENCIA_PACIENTE = 'Porto Alegre' AND MORTE = 1 AND SEXO = 3;[(138,)]Thought: I've executed the query and obtained the result. Now, I need to think about how to answer the question.

Final Answer: The number of women who died in Porto Alegre is 138.
"""

print("🔍 Testing Regex Patterns")
print("=" * 50)

# Test current pattern
sql_result_pattern = r'\[\((\d+),\)\]'
sql_match = re.search(sql_result_pattern, test_response)
print(f"Pattern 1: {sql_result_pattern}")
print(f"Match: {sql_match.group(1) if sql_match else 'NO MATCH'}")

# Test alternative patterns
patterns = [
    r'\[\((\d+),\)\]',  # Current pattern
    r'\[\((\d+)\,\)\]',  # Escaped comma
    r'\[\((\d+).*?\)\]',  # Flexible comma
    r'\[.*?(\d+).*?\]',   # Any number in brackets
]

for i, pattern in enumerate(patterns, 1):
    match = re.search(pattern, test_response)
    print(f"Pattern {i}: {pattern}")
    print(f"Match: {match.group(1) if match else 'NO MATCH'}")
    print()

# Also test Final Answer pattern
final_answer_pattern = r'Final Answer:.*?(\d+)'
final_match = re.search(final_answer_pattern, test_response)
print(f"Final Answer Pattern: {final_answer_pattern}")
print(f"Match: {final_match.group(1) if final_match else 'NO MATCH'}")