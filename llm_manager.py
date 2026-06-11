import os
import json
import requests
import time
from typing import Optional
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

class LLMManager:
    def __init__(self):
        self.openrouter_keys = [os.environ.get(f"OPENROUTER_KEY_{i}") for i in range(1, 7) if os.environ.get(f"OPENROUTER_KEY_{i}")]
        self.gemini_keys = [os.environ.get(f"GEMINI_KEY_{i}") for i in range(1, 7) if os.environ.get(f"GEMINI_KEY_{i}")]
        self.nvidia_keys = [os.environ.get(f"NVIDIA_KEY_{i}") for i in range(1, 7) if os.environ.get(f"NVIDIA_KEY_{i}")]
        
        # Track last call time per provider to enforce rate limits
        # Track last call time per key to enforce rate limits individually
        self.last_call = {}

    def _rate_limit(self, key_identifier: str, min_interval: float = 4.29):
        """Enforces a minimum interval (in seconds) between API calls for a given key."""
        now = time.time()
        if key_identifier not in self.last_call:
            self.last_call[key_identifier] = 0.0
            
        elapsed = now - self.last_call[key_identifier]
        if elapsed < min_interval:
            wait_time = min_interval - elapsed
            print(f"      -> [Rate Limit] Sleeping for {wait_time:.1f}s for key {key_identifier} (14 req/min)...")
            time.sleep(wait_time)
        self.last_call[key_identifier] = time.time()

    def generate(self, prompt: str, system: Optional[str] = None, format: str = "text", temperature: float = 0.0, provider: str = "auto", worker_id: int = None) -> Optional[str]:
        if not self.gemini_keys and not self.openrouter_keys:
            print("      -> [LLM Manager] CRITICAL ERROR: No API keys configured!")
            return None
            
        if worker_id is not None:
            # DEDICATED KEY LOGIC for Multithreading
            gemini_idx = worker_id % max(1, len(self.gemini_keys))
            nvidia_idx = worker_id % max(1, len(self.nvidia_keys)) if self.nvidia_keys else 0
            openrouter_idx = worker_id % max(1, len(self.openrouter_keys))
            
            # Chain: Gemini → NVIDIA → OpenRouter
            if self.gemini_keys and provider in ["auto", "gemini"]:
                g_key = self.gemini_keys[gemini_idx]
                key_id = f"gemini_{gemini_idx}"
                print(f"      -> [LLM Manager] Worker {worker_id+1} using dedicated Gemini Key {gemini_idx+1}...")
                self._rate_limit(key_id)
                res = self._call_gemini(g_key, prompt, system, format, temperature)
                if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s Gemini Key {gemini_idx+1} failed. Failing over to NVIDIA...")
            
            if self.nvidia_keys and provider in ["auto", "nvidia"]:
                n_key = self.nvidia_keys[nvidia_idx]
                key_id = f"nvidia_{nvidia_idx}"
                print(f"      -> [LLM Manager] Worker {worker_id+1} using dedicated NVIDIA Key {nvidia_idx+1}...")
                self._rate_limit(key_id, min_interval=1.0)
                res = self._call_nvidia(n_key, prompt, system, format, temperature)
                if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s NVIDIA Key {nvidia_idx+1} failed. Failing over to OpenRouter...")
                
            if self.openrouter_keys and provider in ["auto", "openrouter"]:
                o_key = self.openrouter_keys[openrouter_idx]
                key_id = f"openrouter_{openrouter_idx}"
                print(f"      -> [LLM Manager] Worker {worker_id+1} using dedicated OpenRouter Key {openrouter_idx+1} as fallback...")
                self._rate_limit(key_id, min_interval=1.0)
                res = self._call_openrouter(o_key, prompt, system, format, temperature)
                if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s OpenRouter Key {openrouter_idx+1} failed.")
                
            return None

        # FALLBACK SEQUENTIAL LOGIC (If worker_id is not provided)
        if provider == "gemini":
            for idx, key in enumerate(self.gemini_keys):
                print(f"      -> [LLM Manager] Trying Gemini Key {idx+1}/{len(self.gemini_keys)} (Requested)...")
                self._rate_limit(f"gemini_{idx}")
                result = self._call_gemini(key, prompt, system, format, temperature)
                if result: return result
                print(f"      -> [LLM Manager] Gemini Key {idx+1} failed. Failing over...")
            return None

        # Provider 1: GEMINI
        for idx, key in enumerate(self.gemini_keys):
            print(f"      -> [LLM Manager] Trying Gemini Key {idx+1}/{len(self.gemini_keys)}...")
            self._rate_limit(f"gemini_{idx}")
            result = self._call_gemini(key, prompt, system, format, temperature)
            if result: return result
            print(f"      -> [LLM Manager] Gemini Key {idx+1} failed. Failing over...")
        
        # Provider 2: NVIDIA
        for idx, key in enumerate(self.nvidia_keys):
            print(f"      -> [LLM Manager] Trying NVIDIA Key {idx+1}/{len(self.nvidia_keys)}...")
            self._rate_limit(f"nvidia_{idx}", min_interval=1.0)
            result = self._call_nvidia(key, prompt, system, format, temperature)
            if result: return result
            print(f"      -> [LLM Manager] NVIDIA Key {idx+1} failed. Failing over...")
            
        # Provider 3: OPENROUTER
        for idx, key in enumerate(self.openrouter_keys):
            print(f"      -> [LLM Manager] Trying OpenRouter Key {idx+1}/{len(self.openrouter_keys)}...")
            self._rate_limit(f"openrouter_{idx}", min_interval=1.0)
            result = self._call_openrouter(key, prompt, system, format, temperature)
            if result: return result
            print(f"      -> [LLM Manager] OpenRouter Key {idx+1} failed. Failing over...")
            
        print("      -> [LLM Manager] CRITICAL ERROR: All API keys for Gemini, NVIDIA, and OpenRouter failed!")
        return None

    def generate_with_image(self, prompt: str, base64_image: str, system: Optional[str] = None, worker_id: int = None) -> Optional[str]:
        """Specific method for Vision using Gemma 4 31B"""
        if not self.gemini_keys: return None
        
        if worker_id is not None:
            idx = worker_id % max(1, len(self.gemini_keys))
            key = self.gemini_keys[idx]
            print(f"      -> [LLM Manager] Thread {worker_id} using dedicated Gemini Vision Key {idx+1}...")
            self._rate_limit(f"gemini_vision_{idx}", min_interval=4.29)
            return self._call_gemini_vision(key, prompt, base64_image, system)

        for idx, key in enumerate(self.gemini_keys):
            print(f"      -> [LLM Manager] Trying Gemini Vision Key {idx+1}/{len(self.gemini_keys)}...")
            self._rate_limit(f"gemini_vision_{idx}", min_interval=4.29)
            result = self._call_gemini_vision(key, prompt, base64_image, system)
            if result: return result
            print(f"      -> [LLM Manager] Gemini Vision Key {idx+1} failed. Failing over...")
        print("      -> [LLM Manager] CRITICAL ERROR: All Gemini keys failed for Vision!")
        return None

    def _call_openrouter(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": "meta-llama/llama-3-70b-instruct", "messages": messages, "temperature": temperature}
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code == 200: return resp.json()["choices"][0]["message"]["content"]
            return None
        except Exception: return None

    def _call_nvidia(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        """Call NVIDIA NIM API with Gemma 4 31B."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": "google/gemma-4-31b-it", "messages": messages, "temperature": temperature, "max_tokens": 4096}
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200: return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] NVIDIA API Error {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] NVIDIA API Exception: {e}")
            return None

    def _call_gemini(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        # Gemma 4 31B for all tasks
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent?key={api_key}"
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

    def _call_gemini_vision(self, api_key: str, prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
        # User requested Gemma 4 31B for vision
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent?key={api_key}"
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
# Global Singleton for easy import
_llm_manager = None
def get_llm_manager():
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager
