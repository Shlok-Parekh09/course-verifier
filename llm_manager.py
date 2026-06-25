import os
import json
import requests
import time
import threading
from typing import Optional
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

class LLMManager:
    def __init__(self):
        self.openrouter_keys = [os.environ.get(f"OPENROUTER_KEY_{i}") for i in range(1, 7) if os.environ.get(f"OPENROUTER_KEY_{i}")]
        self.gemini_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 7) if os.environ.get(f"GEMINI_KEY_{i}")]
        self.nvidia_keys = [os.environ.get(f"NVIDIA_KEY_{i}") for i in range(1, 7) if os.environ.get(f"NVIDIA_KEY_{i}")]
        self.groq_keys = [os.environ.get(f"GROQ_API_KEY_{i}") for i in range(1, 7) if os.environ.get(f"GROQ_API_KEY_{i}")] or ([os.environ.get("GROQ_API_KEY")] if os.environ.get("GROQ_API_KEY") else [])
        self.mistral_keys = [os.environ.get(f"MISTRAL_API_KEY_{i}") for i in range(1, 7) if os.environ.get(f"MISTRAL_API_KEY_{i}")] or ([os.environ.get("MISTRAL_API_KEY")] if os.environ.get("MISTRAL_API_KEY") else [])
        self.sambanova_keys = [os.environ.get(f"SAMBANOVA_API_KEY_{i}") for i in range(1, 7) if os.environ.get(f"SAMBANOVA_API_KEY_{i}")] or ([os.environ.get("SAMBANOVA_API_KEY")] if os.environ.get("SAMBANOVA_API_KEY") else [])
        # Cloud/remote Ollama - must be explicitly set via env vars
        self.cloud_ollama_url = os.environ.get("OLLAMA_API_URL")
        self.cloud_ollama_model = os.environ.get("OLLAMA_MODEL")
        self.ollama_api_key = os.environ.get("OLLAMA_API_KEY")

        # Default to ollama.com if API key is present, else local
        default_url = "https://ollama.com" if self.ollama_api_key else "http://localhost:11434"
        raw_ollama_url = os.environ.get("OLLAMA_API_URL", default_url)
        if raw_ollama_url.endswith("/api/generate"):
            raw_ollama_url = raw_ollama_url[:-13]
        elif raw_ollama_url.endswith("/api"):
            raw_ollama_url = raw_ollama_url[:-4]
        self.ollama_api_url = raw_ollama_url
        self.ollama_model   = os.environ.get("OLLAMA_MODEL", "llama3.3")
        self.ollama_vision_model = os.environ.get("OLLAMA_VISION_MODEL", "gemma4:31b-cloud")

        # Track last call time per provider to enforce rate limits
        # Track last call time per key to enforce rate limits individually
        self.last_call = {}
        self.lock = threading.Lock()

    def _rate_limit(self, key_identifier: str, min_interval: float = 4.29):
        """Enforces a minimum interval (in seconds) between API calls for a given key."""
        with self.lock:
            now = time.time()
            if key_identifier not in self.last_call:
                self.last_call[key_identifier] = 0.0
                
            elapsed = now - self.last_call[key_identifier]
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                print(f"      -> [Rate Limit] Sleeping for {wait_time:.1f}s for key {key_identifier} (14 req/min)...")
                time.sleep(wait_time)
            self.last_call[key_identifier] = time.time()

    def _get_key_sequence(self, worker_id: int, num_keys: int) -> list[int]:
        if num_keys == 0: return []
        return [worker_id % num_keys]

    def generate(self, prompt: str, system: Optional[str] = None, format: str = "text", temperature: float = 0.0, provider: str = "auto", worker_id: int = None, model_name: str = None) -> Optional[str]:
        # Text Generation: Mistral -> NVIDIA -> Gemini -> OpenRouter

        if worker_id is not None:
            # DEDICATED KEY LOGIC for Multithreading
            # Chain: Mistral -> NVIDIA -> Gemini -> OpenRouter (with keys per provider)

            if self.mistral_keys and provider in ["auto", "mistral"]:
                for idx in self._get_key_sequence(worker_id, len(self.mistral_keys)):
                    m_key = self.mistral_keys[idx]
                    key_id = f"mistral_text_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying Mistral Key {idx+1}...")
                    self._rate_limit(key_id, min_interval=1.0)
                    res = self._call_mistral(m_key, prompt, system, format, 0.0)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s Mistral keys failed. Failing over to NVIDIA...")

            if self.nvidia_keys and provider in ["auto", "nvidia"]:
                for idx in self._get_key_sequence(worker_id, len(self.nvidia_keys)):
                    n_key = self.nvidia_keys[idx]
                    key_id = f"nvidia_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying NVIDIA Key {idx+1} (Nemotron Super)...")
                    self._rate_limit(key_id, min_interval=1.0)
                    res = self._call_nvidia(n_key, prompt, system, format, 0.0)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s NVIDIA keys failed. Failing over to Gemini...")

            if self.gemini_keys and provider in ["auto", "gemini"]:
                for idx in self._get_key_sequence(worker_id, len(self.gemini_keys)):
                    g_key = self.gemini_keys[idx]
                    key_id = f"gemini_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying Gemini Key {idx+1}...")
                    self._rate_limit(key_id)
                    res = self._call_gemini(g_key, prompt, system, format, 0.0, model_name=model_name)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s Gemini keys failed. Failing over to OpenRouter...")

            if self.openrouter_keys and provider in ["auto", "openrouter"]:
                for idx in self._get_key_sequence(worker_id, len(self.openrouter_keys)):
                    o_key = self.openrouter_keys[idx]
                    key_id = f"openrouter_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying OpenRouter Key {idx+1}...")
                    self._rate_limit(key_id, min_interval=1.0)
                    res = self._call_openrouter(o_key, prompt, system, format, 0.0)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s OpenRouter keys failed.")



            return None

        # FALLBACK SEQUENTIAL LOGIC (If worker_id is not provided)
        # Provider 0: MISTRAL
        if provider in ["auto", "mistral"]:
            for idx, key in enumerate(self.mistral_keys):
                print(f"      -> [LLM Manager] Trying Mistral Key {idx+1}/{len(self.mistral_keys)}...")
                self._rate_limit(f"mistral_text_{idx}", min_interval=1.0)
                result = self._call_mistral(key, prompt, system, format, 0.0)
                if result: return result
                print(f"      -> [LLM Manager] Mistral Key {idx+1} failed. Failing over...")

        # Provider 1: NVIDIA
        if provider in ["auto", "nvidia"]:
            for idx, key in enumerate(self.nvidia_keys):
                print(f"      -> [LLM Manager] Trying NVIDIA Key {idx+1}/{len(self.nvidia_keys)} (Nemotron Super)...")
                self._rate_limit(f"nvidia_{idx}", min_interval=1.0)
                result = self._call_nvidia(key, prompt, system, format, 0.0)
                if result: return result
                print(f"      -> [LLM Manager] NVIDIA Key {idx+1} failed. Failing over...")

        # Provider 2: GEMINI
        if provider in ["auto", "gemini"]:
            for idx, key in enumerate(self.gemini_keys):
                print(f"      -> [LLM Manager] Trying Gemini Key {idx+1}/{len(self.gemini_keys)}...")
                self._rate_limit(f"gemini_{idx}")
                result = self._call_gemini(key, prompt, system, format, 0.0, model_name=model_name)
                if result: return result
                print(f"      -> [LLM Manager] Gemini Key {idx+1} failed. Failing over...")

        # Provider 3: OPENROUTER
        if provider in ["auto", "openrouter"]:
            for idx, key in enumerate(self.openrouter_keys):
                print(f"      -> [LLM Manager] Trying OpenRouter Key {idx+1}/{len(self.openrouter_keys)}...")
                self._rate_limit(f"openrouter_{idx}", min_interval=1.0)
                result = self._call_openrouter(key, prompt, system, format, 0.0)
                if result: return result
                print(f"      -> [LLM Manager] OpenRouter Key {idx+1} failed. Failing over...")



        print("      -> [LLM Manager] CRITICAL ERROR: All API keys for Mistral, NVIDIA, Gemini, and OpenRouter failed!")
        return None

    def generate_with_image(self, prompt: str, base64_image: str, system: Optional[str] = None, worker_id: int = None) -> Optional[str]:
        """Method for Vision extraction using Groq, Mistral, and SambaNova"""
        
        if worker_id is not None:
            # DEDICATED KEY LOGIC for Multithreading Vision
            # Chain: Groq → Mistral → SambaNova (with 2 keys per provider)
            
            if self.groq_keys:
                for idx in self._get_key_sequence(worker_id, len(self.groq_keys)):
                    g_key = self.groq_keys[idx]
                    key_id = f"groq_vision_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying Groq Vision Key {idx+1} (Qwen 3.6 27B)...")
                    self._rate_limit(key_id, min_interval=4.0) # 15 RPM
                    res = self._call_groq_vision(g_key, prompt, base64_image, system)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s Groq Vision keys failed. Failing over to Mistral...")

            if self.mistral_keys:
                for idx in self._get_key_sequence(worker_id, len(self.mistral_keys)):
                    m_key = self.mistral_keys[idx]
                    key_id = f"mistral_vision_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying Mistral Vision Key {idx+1}...")
                    self._rate_limit(key_id, min_interval=1.0) # 60 RPM
                    res = self._call_mistral_vision(m_key, prompt, base64_image, system)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s Mistral Vision keys failed. Failing over to SambaNova...")
            
            if self.sambanova_keys:
                for idx in self._get_key_sequence(worker_id, len(self.sambanova_keys)):
                    s_key = self.sambanova_keys[idx]
                    key_id = f"sambanova_vision_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying SambaNova Vision Key {idx+1}...")
                    self._rate_limit(key_id, min_interval=2.0) # 30 RPM
                    res = self._call_sambanova_vision(s_key, prompt, base64_image, system)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s SambaNova Vision keys failed.")
                
            return None
        
        max_keys = max(len(self.groq_keys), len(self.mistral_keys), len(self.sambanova_keys))
        
        for idx in range(max_keys):
            # 1. Try Groq (Llama 4 Scout Vision)
            if idx < len(self.groq_keys):
                key = self.groq_keys[idx]
                print(f"      -> [LLM Manager] Trying Groq Vision Key {idx+1}/{len(self.groq_keys)} (Qwen 3.6 27B)...")
                self._rate_limit(f"groq_vision_{idx}", min_interval=4.0) # 15 RPM
                result = self._call_groq_vision(key, prompt, base64_image, system)
                if result: return result
                print(f"      -> [LLM Manager] Groq Vision Key {idx+1} failed. Failing over...")
            
            # 2. Try Mistral (Pixtral 12B Vision)
            if idx < len(self.mistral_keys):
                key = self.mistral_keys[idx]
                print(f"      -> [LLM Manager] Trying Mistral Vision Key {idx+1}/{len(self.mistral_keys)}...")
                self._rate_limit(f"mistral_vision_{idx}", min_interval=1.0) # 60 RPM
                result = self._call_mistral_vision(key, prompt, base64_image, system)
                if result: return result
                print(f"      -> [LLM Manager] Mistral Vision Key {idx+1} failed. Failing over...")
            
            # 3. Try SambaNova (Llama 3.2 11B Vision)
            if idx < len(self.sambanova_keys):
                key = self.sambanova_keys[idx]
                print(f"      -> [LLM Manager] Trying SambaNova Vision Key {idx+1}/{len(self.sambanova_keys)}...")
                self._rate_limit(f"sambanova_vision_{idx}", min_interval=2.0) # 30 RPM
                result = self._call_sambanova_vision(key, prompt, base64_image, system)
                if result: return result
                print(f"      -> [LLM Manager] SambaNova Vision Key {idx+1} failed. Failing over...")
                
        print("      -> [LLM Manager] CRITICAL ERROR: All Groq, Mistral, and SambaNova keys failed for Vision!")
        return None

    def _call_ollama(self, prompt: str, system: Optional[str], format: str, temperature: float, *, url: str = None, model: str = None) -> Optional[str]:
        if not url: url = f"{self.ollama_api_url}/api/generate"
        if not model: model = self.ollama_model
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0
            }
        }
        if system:
            payload["system"] = system
        if format == "json":
            payload["format"] = "json"
            
        try:
            headers = {"Content-Type": "application/json"}
            if self.ollama_api_key:
                headers["Authorization"] = f"Bearer {self.ollama_api_key}"
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.json().get("response")
            return None
        except Exception:
            return None

    def _call_openrouter(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": "meta-llama/llama-3.3-70b-instruct:free", "messages": messages, "temperature": temperature}
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200: return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] OpenRouter API Error {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e: 
            print(f"      -> [LLM Manager] OpenRouter API Exception: {e}")
            return None

    def _call_nvidia(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        """Call NVIDIA NIM API with Llama 3.3 70B."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": "nvidia/nemotron-3-super-120b-a12b", "messages": messages, "temperature": temperature, "max_tokens": 4096}
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200: return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] NVIDIA API Error {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] NVIDIA API Exception: {e}")
            return None

    def _call_gemini(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float, model_name: str = None) -> Optional[str]:
        # Gemma 4 31B for text verification (user requested exact string)
        if not model_name:
            model_name = "gemma-4-31b-it"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        parts = []
        if system: parts.append({"text": f"System Instructions: {system}\n\n"})
        parts.append({"text": prompt})
        
        payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": temperature}}
        if format == "json": payload["generationConfig"]["responseMimeType"] = "application/json"
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=300)
            if resp.status_code == 200: return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"      -> [LLM Manager] Gemini API Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Gemini API Exception: {e}")
            return None

    def _call_groq(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": temperature
        }
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] Groq API Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Groq API Exception: {e}")
            return None

    def _call_sambanova(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        url = "https://api.sambanova.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "Meta-Llama-3.1-70B-Instruct",
            "messages": messages,
            "temperature": temperature
        }
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] SambaNova API Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] SambaNova API Exception: {e}")
            return None

    def _call_mistral(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "mistral-large-latest",
            "messages": messages,
            "temperature": temperature
        }
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] Mistral API Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Mistral API Exception: {e}")
            return None

    def _call_gemini_vision(self, api_key: str, prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        parts = []
        if system: parts.append({"text": f"System Instructions: {system}\n\n"})
        parts.append({"text": prompt})
        
        # Deduce mime type
        mime_type = "image/png"
        if base64_image.startswith("/9j/"): mime_type = "image/jpeg"
        
        parts.append({"inline_data": {"mime_type": mime_type, "data": base64_image}})
        
        payload = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.0}}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=300)
            if resp.status_code == 200: return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"      -> [LLM Manager] Gemini Vision Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e: 
            print(f"      -> [LLM Manager] Gemini Vision Exception: {e}")
            return None

    def _call_groq_vision(self, api_key: str, prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]})
        payload = {
            "model": "qwen/qwen3.6-27b",
            "messages": messages,
            "temperature": 0.0
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"Groq API Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Groq Error: {e}")
        return None

    def _call_mistral_vision(self, api_key: str, prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{base64_image}"}
        ]})
        payload = {
            "model": "pixtral-large-2411",
            "messages": messages,
            "temperature": 0.0
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"Mistral API Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Mistral Error: {e}")
        return None

    def _call_sambanova_vision(self, api_key: str, prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
        url = "https://api.sambanova.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]})
        payload = {
            "model": "Llama-3.2-90B-Vision-Instruct",
            "messages": messages,
            "temperature": 0.0
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"SambaNova API Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"SambaNova Error: {e}")
        return None

    def _call_ollama_vision(self, prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
        url = f"{self.ollama_api_url}/api/generate"
        payload = {
            "model": self.ollama_vision_model,
            "prompt": prompt,
            "stream": False,
            "images": [base64_image],
            "options": {
                "temperature": 0.0
            }
        }
        if system:
            payload["system"] = system
            
        try:
            headers = {"Content-Type": "application/json"}
            if self.ollama_api_key:
                headers["Authorization"] = f"Bearer {self.ollama_api_key}"
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.json().get("response")
            else:
                print(f"      -> [LLM Manager] Ollama Vision Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Ollama Vision Exception: {e}")
            return None

# Global Singleton for easy import
_llm_manager = None
def get_llm_manager():
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager
