import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_puter_api():
    puter_key = os.environ.get("PUTER_KEY_1")
    if not puter_key:
        print("[Error] PUTER_KEY_1 not found in .env")
        return

    url = "https://api.puter.com/puterai/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {puter_key}",
        "Content-Type": "application/json"
    }
    
    # Using Gemini 3.1 Pro as requested
    payload = {
        "model": "gemini-3.1-pro-preview",
        "messages": [
            {"role": "user", "content": "Hello! Reply with exactly 'TEST_SUCCESS' if you receive this."}
        ],
        "temperature": 0.0
    }

    print(f"Testing Puter API with key: {puter_key[:8]}... Using model: gemini-3.1-pro-preview")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            print("[Success] Response:")
            print(response.json()["choices"][0]["message"]["content"])
        else:
            print(f"[Failed] Status Code: {response.status_code}")
            print(response.text)
            
            # Fallback test
            print("\nTrying again with model 'google/gemini-3.1-pro'...")
            payload["model"] = "google/gemini-3.1-pro"
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                print("[Success] with 'google/gemini-3.1-pro'!")
                print(response.json()["choices"][0]["message"]["content"])
            else:
                print(f"[Failed] again! Status Code: {response.status_code}")
                print(response.text)
                
    except Exception as e:
        print(f"[Error] connecting to Puter API: {e}")

if __name__ == "__main__":
    test_puter_api()
