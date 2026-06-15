import requests
import json
import time

API_URL = "http://localhost:8000/execute"
HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": "change-me-before-deploy"
}

# The same user_id should persist the DB
PAYLOAD_CREATE = {
    "language": "sql",
    "source_code": "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT); INSERT INTO users (name) VALUES ('Alice'); SELECT * FROM users;",
    "user_id": "test_user_123"
}

PAYLOAD_QUERY = {
    "language": "sql",
    "source_code": "INSERT INTO users (name) VALUES ('Bob'); SELECT * FROM users;",
    "user_id": "test_user_123"
}

def run_test():
    print("--- 1. Creating table and inserting first row ---")
    response1 = requests.post(API_URL, headers=HEADERS, json=PAYLOAD_CREATE)
    print("Response Status:", response1.status_code)
    try:
        print("Stdout:\n", response1.json().get("stdout", ""))
        print("Stderr:\n", response1.json().get("stderr", ""))
    except Exception as e:
        print("Error parsing JSON:", e)

    print("\nWaiting 2 seconds...\n")
    time.sleep(2)

    print("--- 2. Inserting second row and querying (Should see both Alice and Bob) ---")
    response2 = requests.post(API_URL, headers=HEADERS, json=PAYLOAD_QUERY)
    print("Response Status:", response2.status_code)
    try:
        print("Stdout:\n", response2.json().get("stdout", ""))
        print("Stderr:\n", response2.json().get("stderr", ""))
    except Exception as e:
        print("Error parsing JSON:", e)

if __name__ == "__main__":
    run_test()
