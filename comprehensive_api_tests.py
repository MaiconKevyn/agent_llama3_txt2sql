#!/usr/bin/env python3
"""
Comprehensive API Test Suite for TXT2SQL
Tests all API endpoints with various scenarios
"""

import requests
import json
import time
import sys
import os
from datetime import datetime
from typing import Dict, Any, List

class APITester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.results = []
        
    def log_test(self, test_name: str, success: bool, details: str = "", response_time: float = 0):
        """Log test result"""
        result = {
            "test": test_name,
            "success": success,
            "details": details,
            "response_time": response_time,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {details}")
        if response_time > 0:
            print(f"   ⏱️  Response time: {response_time:.2f}s")
    
    def test_health_endpoint(self) -> bool:
        """Test health check endpoint"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/health")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                self.log_test("Health Check", True, f"Status: {data.get('status')}", response_time)
                return True
            else:
                self.log_test("Health Check", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Health Check", False, f"Exception: {str(e)}")
            return False
    
    def test_schema_endpoint(self) -> bool:
        """Test schema endpoint"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/schema")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                schema = data.get('schema', '')
                self.log_test("Schema Endpoint", True, f"Schema length: {len(schema)} chars", response_time)
                return True
            else:
                self.log_test("Schema Endpoint", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Schema Endpoint", False, f"Exception: {str(e)}")
            return False
    
    def test_query_endpoint(self, question: str, expected_success: bool = True) -> bool:
        """Test query endpoint with specific question"""
        try:
            start_time = time.time()
            payload = {"question": question}
            response = self.session.post(f"{self.base_url}/query", json=payload)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                success = data.get('success', False)
                
                if success == expected_success:
                    result_info = f"Rows: {data.get('row_count', 0)}"
                    if data.get('sql_query'):
                        result_info += f" | SQL: {data['sql_query'][:50]}..."
                    self.log_test(f"Query: {question[:30]}...", True, result_info, response_time)
                    return True
                else:
                    error_msg = data.get('error_message', 'Unknown error')
                    self.log_test(f"Query: {question[:30]}...", False, f"Unexpected result. Error: {error_msg}")
                    return False
            else:
                self.log_test(f"Query: {question[:30]}...", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test(f"Query: {question[:30]}...", False, f"Exception: {str(e)}")
            return False
    
    def test_models_endpoint(self) -> bool:
        """Test models endpoint"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/models")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                self.log_test("Models Endpoint", True, f"Available models: {models}", response_time)
                return True
            else:
                self.log_test("Models Endpoint", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Models Endpoint", False, f"Exception: {str(e)}")
            return False
    
    def test_root_endpoint(self) -> bool:
        """Test root endpoint (HTML interface)"""
        try:
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/")
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                content_length = len(response.text)
                self.log_test("Root Endpoint", True, f"HTML interface loaded ({content_length} chars)", response_time)
                return True
            else:
                self.log_test("Root Endpoint", False, f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_test("Root Endpoint", False, f"Exception: {str(e)}")
            return False
    
    def test_error_cases(self) -> bool:
        """Test various error cases"""
        all_passed = True
        
        # Test empty query
        try:
            payload = {"question": ""}
            response = self.session.post(f"{self.base_url}/query", json=payload)
            if response.status_code == 400:
                self.log_test("Empty Query Error", True, "Correctly rejected empty query")
            else:
                self.log_test("Empty Query Error", False, f"Unexpected status: {response.status_code}")
                all_passed = False
        except Exception as e:
            self.log_test("Empty Query Error", False, f"Exception: {str(e)}")
            all_passed = False
        
        # Test malformed JSON
        try:
            response = requests.post(
                f"{self.base_url}/query",
                data="invalid json",
                headers={"Content-Type": "application/json"}
            )
            if response.status_code == 422:
                self.log_test("Malformed JSON Error", True, "Correctly rejected malformed JSON")
            else:
                self.log_test("Malformed JSON Error", False, f"Unexpected status: {response.status_code}")
                all_passed = False
        except Exception as e:
            self.log_test("Malformed JSON Error", False, f"Exception: {str(e)}")
            all_passed = False
        
        return all_passed
    
    def run_performance_tests(self) -> bool:
        """Run performance tests"""
        print("\n🚀 Running Performance Tests...")
        
        # Test concurrent queries
        import threading
        import queue
        
        results_queue = queue.Queue()
        
        def worker():
            try:
                start = time.time()
                response = self.session.post(
                    f"{self.base_url}/query",
                    json={"question": "How many patients are there?"}
                )
                end = time.time()
                results_queue.put(("success", end - start, response.status_code))
            except Exception as e:
                results_queue.put(("error", 0, str(e)))
        
        # Start 5 concurrent requests
        threads = []
        start_time = time.time()
        
        for i in range(5):
            t = threading.Thread(target=worker)
            t.start()
            threads.append(t)
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        total_time = time.time() - start_time
        
        # Collect results
        successes = 0
        total_response_time = 0
        
        while not results_queue.empty():
            status, response_time, code = results_queue.get()
            if status == "success" and code == 200:
                successes += 1
                total_response_time += response_time
        
        if successes > 0:
            avg_response_time = total_response_time / successes
            self.log_test(
                "Concurrent Queries", 
                successes >= 3, 
                f"{successes}/5 successful, avg: {avg_response_time:.2f}s, total: {total_time:.2f}s"
            )
            return successes >= 3
        else:
            self.log_test("Concurrent Queries", False, "No successful requests")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        print("🧪 Starting Comprehensive API Tests...")
        print(f"🎯 Target: {self.base_url}")
        print("=" * 60)
        
        # Basic endpoint tests
        print("\n📋 Basic Endpoint Tests:")
        basic_tests = [
            self.test_health_endpoint(),
            self.test_root_endpoint(),
            self.test_models_endpoint(),
            self.test_schema_endpoint()
        ]
        
        # Query tests
        print("\n💬 Query Tests:")
        test_queries = [
            "How many patients are there?",
            "What is the average age of patients?",
            "Show me 5 patients from Porto Alegre",
            "How many deaths occurred?",
            "What are the most common diagnoses?",
        ]
        
        query_tests = []
        for query in test_queries:
            query_tests.append(self.test_query_endpoint(query))
        
        # Error handling tests
        print("\n⚠️  Error Handling Tests:")
        error_tests = [self.test_error_cases()]
        
        # Performance tests
        performance_tests = [self.run_performance_tests()]
        
        # Calculate results
        all_tests = basic_tests + query_tests + error_tests + performance_tests
        passed = sum(all_tests)
        total = len(all_tests)
        
        print("\n" + "=" * 60)
        print(f"📊 Test Results: {passed}/{total} passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 All tests passed!")
        elif passed >= total * 0.8:
            print("⚠️  Most tests passed - minor issues detected")
        else:
            print("❌ Significant issues detected")
        
        return {
            "total_tests": total,
            "passed_tests": passed,
            "success_rate": passed/total*100,
            "results": self.results
        }

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Comprehensive API Test Suite")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--output", help="Output file for detailed results (JSON)")
    parser.add_argument("--quick", action="store_true", help="Run only basic tests")
    
    args = parser.parse_args()
    
    tester = APITester(args.url)
    
    if args.quick:
        print("🏃 Running Quick Tests...")
        tester.test_health_endpoint()
        tester.test_query_endpoint("How many patients are there?")
    else:
        results = tester.run_all_tests()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"📄 Detailed results saved to {args.output}")
    
    return 0 if all(r["success"] for r in tester.results) else 1

if __name__ == "__main__":
    sys.exit(main())