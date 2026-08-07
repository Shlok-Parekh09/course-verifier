import os
import sys
import json
import requests
import time
import threading
from typing import Optional
from dotenv import load_dotenv

# Load .env variables
import os; load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

class LLMManagerAPI:
    def _parse_keys(self, prefix: str) -> list[str]:
        keys = []
        plural_env = os.environ.get(f"{prefix}_API_KEYS") or os.environ.get(f"{prefix}_KEYS")
        if plural_env:
            keys = [k.strip() for k in plural_env.split(",") if k.strip()]
        if not keys:
            keys = [os.environ.get(f"{prefix}_API_KEY_{i}") for i in range(1, 51) if os.environ.get(f"{prefix}_API_KEY_{i}")]
        if not keys:
            keys = [os.environ.get(f"{prefix}_KEY_{i}") for i in range(1, 51) if os.environ.get(f"{prefix}_KEY_{i}")]
        if not keys:
            singular = os.environ.get(f"{prefix}_API_KEY") or os.environ.get(f"{prefix}_KEY")
            if singular:
                keys = [singular]
        return keys

    def __init__(self):
        self.github_keys = self._parse_keys("GITHUB")
        self.nvidia_keys = self._parse_keys("NVIDIA")
        self.hf_urls = [os.environ.get(f"HF_OLLAMA_URL_{i}") for i in range(1, 51) if os.environ.get(f"HF_OLLAMA_URL_{i}")]
        self._hf_clients = {}
        self.groq_keys = self._parse_keys("GROQ")
        self.mistral_keys = self._parse_keys("MISTRAL")
        self.sambanova_keys = self._parse_keys("SAMBANOVA")
        self.gemini_keys = self._parse_keys("GEMINI")
        
        # Cloud/remote Ollama - must be explicitly set via env vars
        self.cloud_ollama_url = os.environ.get("OLLAMA_API_URL")
        self.cloud_ollama_model = os.environ.get("OLLAMA_MODEL")
        self.ollama_api_key = os.environ.get("OLLAMA_API_KEY")

        # In API mode, we do NOT default to localhost. We only use Ollama if URL is explicitly provided.
        self.backend_mode = os.environ.get("LLM_BACKEND", "api").lower().strip()
        raw_ollama_url = os.environ.get("OLLAMA_API_URL")
        if not raw_ollama_url and self.ollama_api_key:
            raw_ollama_url = "https://ollama.com"
        self.vision_call_counter = 0
        self._vision_lock = threading.Lock()
        if raw_ollama_url and raw_ollama_url.endswith("/api/generate"):
            raw_ollama_url = raw_ollama_url[:-13]
        elif raw_ollama_url and raw_ollama_url.endswith("/api"):
            raw_ollama_url = raw_ollama_url[:-4]
        self.ollama_api_url = raw_ollama_url
        self.ollama_model   = os.environ.get("OLLAMA_MODEL", "mistral-large-3:675b-cloud")
        self.ollama_vision_model = os.environ.get("OLLAMA_VISION_MODEL", "qwen3.5:cloud")

        # Track last call time per provider to enforce rate limits
        # Track last call time per key to enforce rate limits individually
        self.last_call = {}
        self.lock = threading.Lock()

        # ── Diagnostic logging ──
        print(f"[LLM Manager] Keys loaded: Mistral={len(self.mistral_keys)}, NVIDIA={len(self.nvidia_keys)}, "
              f"Gemini={len(self.gemini_keys)}, GitHub={len(self.github_keys)}, "
              f"Groq={len(self.groq_keys)}, HF_Ollama={len(self.hf_urls)}, "
              f"Cloud_Ollama={'yes' if self.ollama_api_url else 'no'} (mode={self.backend_mode})")
        if "ollama" in self.backend_mode and not self.ollama_api_url:
            print("[LLM Manager] ⚠ CRITICAL WARNING: You selected Ollama mode but did NOT provide an OLLAMA_API_URL or OLLAMA_API_KEY in your .env! Ollama calls will silently fail.")
        elif not any([self.mistral_keys, self.nvidia_keys, self.gemini_keys, self.github_keys, self.groq_keys, self.ollama_api_url, self.hf_urls]):
            print("[LLM Manager] ⚠ WARNING: No text-generation API keys or Ollama URL found! All LLM calls will return None.")

    def _rate_limit(self, key_identifier: str, min_interval: float = 4.29):
        """Enforces a minimum interval (in seconds) between API calls for a given key.
        IMPORTANT: sleep is done OUTSIDE the lock so other threads are not blocked."""
        wait_time = 0.0
        with self.lock:
            now = time.time()
            if key_identifier not in self.last_call:
                self.last_call[key_identifier] = 0.0
            elapsed = now - self.last_call[key_identifier]
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
            # Mark the call time NOW (under lock) so parallel threads on different
            # keys don't all see elapsed=0 and skip the rate limit.
            self.last_call[key_identifier] = time.time() + wait_time
        if wait_time > 0:
            print(f"      -> [Rate Limit] Sleeping for {wait_time:.1f}s for key {key_identifier} (14 req/min)...")
            time.sleep(wait_time)

    def _get_key_sequence(self, worker_id: int, num_keys: int, num_workers: int = 0) -> list[int]:
        """Return the ordered list of key indices this worker should try.
        
        Uses a SPREAD pattern so each worker gets keys from opposite ends of the
        list (e.g. 6 keys, 3 workers → worker 0: [0,5], worker 1: [1,4], worker 2: [2,3]).
        This maximises the gap between consecutive calls on the same key, naturally
        avoiding rate-limit collisions without explicit sleeping.
        """
        if num_keys == 0:
            return []
        # Read actual browser/worker count from env so the pattern always matches
        if num_workers <= 0:
            try:
                num_workers = int(os.environ.get("VERIFIER_NUM_BROWSERS", "3"))
            except (ValueError, TypeError):
                num_workers = 3
        if num_workers <= 0:
            num_workers = 3

        w = worker_id % num_workers
        keys = []
        # Assign keys from the front and mirrored from the back for this worker
        for offset in range(0, num_keys, num_workers):
            front_idx = offset + w
            back_idx  = num_keys - 1 - offset - w
            if front_idx < num_keys:
                keys.append(front_idx)
            if back_idx >= 0 and back_idx != front_idx and back_idx not in keys:
                keys.append(back_idx)
        return keys if keys else [w % num_keys]

    def _check_token_error(self, text: str) -> bool:
        err = text.lower()
        return "context" in err or "token" in err or "too large" in err or "exceeds" in err

    def generate(self, prompt: str, system: Optional[str] = None, format: str = "text", temperature: float = 0.0, provider: str = "auto", worker_id: Optional[int] = None, model_name: Optional[str] = None, timeout: int = 120) -> Optional[str]:
        # Text Generation with round-robin provider rotation.
        # When worker_id is given each worker starts at a different provider so all
        # providers (Mistral, Groq, OpenRouter, NVIDIA, Gemini) get used equally
        # rather than NVIDIA/Gemini only being reached as last-resort fallbacks.

        if worker_id is not None:
            # Build the ordered provider list for this specific call.
            # Each provider entry is (name, keys_list, rate_interval, call_fn)
            provider_pool = []
            if self.backend_mode == "ollama":
                # Cloud Ollama (ollama.com with API key) — PRIMARY when OLLAMA_API_URL is set
                if self.ollama_api_url:
                    # Wrap URL in a list so it integrates with the round-robin pool structure.
                    # The _call_ollama method will be called with the URL as the "key".
                    provider_pool.append(("Cloud Ollama", [self.ollama_api_url], 1.0, "cloud_ollama"))
                # HF Ollama Spaces — additional capacity
                if self.hf_urls:
                    provider_pool.append(("Local Ollama (HF)", self.hf_urls, 1.0, "local_ollama"))

            # STRICT ISOLATION: Do not add API keys if the user specifically requested Local Ollama
            if self.backend_mode != "ollama" and provider != "ollama":
                if self.mistral_keys:
                    # Append Mistral FIRST to heavily prioritize it as requested
                    provider_pool.insert(0, ("Mistral", self.mistral_keys, 1.0, "mistral"))
                
                if self.groq_keys:
                    provider_pool.append(("Groq (Llama 3.3 70B)", self.groq_keys, 4.0, "groq"))
                if self.nvidia_keys:
                    provider_pool.append(("NVIDIA (Mistral Medium 3.5 128B)", self.nvidia_keys, 1.0, "nvidia"))
                # Cloud Ollama as additional provider in API mode (when OLLAMA_API_URL is configured)
                if self.ollama_api_url:
                    provider_pool.append(("Cloud Ollama", [self.ollama_api_url], 1.0, "cloud_ollama"))

            if not provider_pool:
                print(f"      -> [LLM Manager] Worker {worker_id+1}: No API keys available!")
                return None

            # Filter by explicit provider request
            if provider != "auto" and provider != "ollama":
                provider_pool = [p for p in provider_pool if p[3] == provider] or provider_pool

            # Disable provider round-robin to ensure Mistral is ALWAYS prioritized first
            # The keys themselves are still load-balanced across workers.
            start = 0

            for offset in range(len(provider_pool)):
                p_name, p_keys, p_rate, p_tag = provider_pool[(start + offset) % len(provider_pool)]
                for idx in self._get_key_sequence(worker_id, len(p_keys)):
                    key_id = f"{p_tag}_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying {p_name} Key {idx+1}...")
                    self._rate_limit(key_id, min_interval=p_rate)
                    if p_tag == "mistral":
                        res = self._call_mistral(p_keys[idx], prompt, system, format, 0.0)
                    elif p_tag == "groq":
                        res = self._call_groq(p_keys[idx], prompt, system, format, 0.0)
                    elif p_tag == "nvidia":
                        res = self._call_nvidia(p_keys[idx], prompt, system, format, 0.0, timeout=timeout)
                    elif p_tag == "cloud_ollama":
                        res = self._call_ollama(prompt, system, format, 0.0, url=p_keys[idx], timeout=timeout)
                    elif p_tag == "local_ollama":
                        res = self._call_local_ollama(p_keys[idx], prompt, system, format, 0.0, is_vision=False)
                    else:
                        res = None
                    if res:
                        return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s {p_name} keys failed. Trying next provider...")

            # FINAL FALLBACK TO GITHUB MODELS (Last resort)
            if self.github_keys:
                print(f"      -> [LLM Manager] Worker {worker_id+1} all standard providers failed. Falling back to GitHub Models...")
                for idx, key in enumerate(self.github_keys):
                    self._rate_limit(f"github_{idx}", min_interval=1.0)
                    res = self._call_github(key, prompt, system, format, 0.0)
                    if res: return res

            print(f"      -> [LLM Manager] Worker {worker_id+1}: ALL providers exhausted!")
            return None

        # FALLBACK SEQUENTIAL LOGIC (If worker_id is not provided)
        # Provider: OLLAMA
        if provider in ["auto", "ollama"] and self.ollama_api_url:
            print(f"      -> [LLM Manager] Trying Ollama ({self.ollama_model})...")
            result = self._call_ollama(prompt, system, format, temperature, url=self.ollama_api_url, model=self.ollama_model, timeout=timeout)
            if result: return result
            print(f"      -> [LLM Manager] Ollama failed. Failing over...")
            
        # STRICT ISOLATION: Do not proceed to APIs if Local/Cloud Ollama was requested
        if "ollama" in self.backend_mode or provider == "ollama":
            print("      -> [LLM Manager] Ollama exhausted or URL missing (APIs disabled). Returning None.")
            return None

        # Provider 0: MISTRAL
        if provider in ["auto", "mistral"]:
            for idx, key in enumerate(self.mistral_keys):
                print(f"      -> [LLM Manager] Trying Mistral Key {idx+1}/{len(self.mistral_keys)}...")
                self._rate_limit(f"mistral_text_{idx}", min_interval=1.0)
                result = self._call_mistral(key, prompt, system, format, 0.0)
                if result: return result
                print(f"      -> [LLM Manager] Mistral Key {idx+1} failed. Failing over...")

        # Provider 1: GROQ
        if provider in ["auto", "groq"]:
            for idx, key in enumerate(self.groq_keys):
                print(f"      -> [LLM Manager] Trying Groq Key {idx+1}/{len(self.groq_keys)} (Llama 3.3 70B)...")
                self._rate_limit(f"groq_{idx}", min_interval=4.0)
                result = self._call_groq(key, prompt, system, format, 0.0)
                if result: return result
                print(f"      -> [LLM Manager] Groq Key {idx+1} failed. Failing over...")

        # Provider 4: NVIDIA
        if provider in ["auto", "nvidia"]:
            for idx, key in enumerate(self.nvidia_keys):
                print(f"      -> [LLM Manager] Trying NVIDIA Key {idx+1}/{len(self.nvidia_keys)} (Mistral Medium 3.5 128B)...")
                self._rate_limit(f"nvidia_{idx}", min_interval=1.0)
                result = self._call_nvidia(key, prompt, system, format, 0.0, timeout=timeout)
                if result: return result
                print(f"      -> [LLM Manager] NVIDIA Key {idx+1} failed. Failing over...")

        # Provider 5: GitHub Models (Final text fallback)
        if provider in ["auto", "github"]:
            for idx, key in enumerate(self.github_keys):
                print(f"      -> [LLM Manager] Trying GitHub Key {idx+1}/{len(self.github_keys)} (Llama-3.3-70B-Instruct)...")
                self._rate_limit(f"github_{idx}", min_interval=1.0)
                result = self._call_github(key, prompt, system, format, 0.0)
                if result: return result
                print(f"      -> [LLM Manager] GitHub Key {idx+1} failed. Failing over...")

        print("      -> [LLM Manager] CRITICAL ERROR: All API keys for Mistral, Groq, NVIDIA, and GitHub failed!")
        return None

    def generate_with_image(self, prompt: str, base64_image: str, system: Optional[str] = None, worker_id: Optional[int] = None) -> Optional[str]:
        """Method for Vision extraction using Mistral, Gemini, and SambaNova"""
        
        with self._vision_lock:
            current_call_idx = self.vision_call_counter
            self.vision_call_counter += 1

        print(f"      -> [LLM Manager] Vision call index: {current_call_idx}")

        max_g = len(self.gemini_keys)
        max_m = len(self.mistral_keys)
        max_keys = max(max_g, max_m)
        
        if self.backend_mode == "ollama":
            if self.ollama_api_url:
                print(f"      -> [LLM Manager] Trying Ollama Vision ({self.ollama_vision_model})...")
                res = self._call_ollama_vision(prompt, base64_image, system)
                if res: return res
                print("      -> [LLM Manager] Ollama Vision failed. Failing over to HF Spaces...")
                
            if self.hf_urls:
                print(f"      -> [LLM Manager] Trying Local Ollama Vision (Qwen) via Dedicated HF Space...")
                for v_url in reversed(self.hf_urls):
                    res = self._call_local_ollama(v_url, prompt, system, "text", 0.0, is_vision=True, base64_image=base64_image)
                    if res: return res
                print("      -> [LLM Manager] Local Ollama Vision failed.")
                
            print("      -> [LLM Manager] Local Ollama Vision exhausted (APIs disabled). Returning None.")
            return None
        
        # We are in API mode.
        if max_keys == 0:
            print("      -> [LLM Manager] CRITICAL ERROR: No API keys for Vision!")
            return None

        start_key_idx = current_call_idx % max_keys
        
        for offset in range(max_keys):
            key_idx = (start_key_idx + offset) % max_keys
            
            if key_idx < max_g:
                key = self.gemini_keys[key_idx]
                key_id = f"gemini_vision_{key_idx}"
                print(f"      -> [LLM Manager] Trying Gemini Vision Key {key_idx+1}/{max_g}...")
                self._rate_limit(key_id, min_interval=4.0)
                result = self._call_gemini_vision(key, prompt, base64_image, system)
                if result: return result
                print(f"      -> [LLM Manager] Gemini Vision Key {key_idx+1} failed.")
                
            if key_idx < max_m:
                key = self.mistral_keys[key_idx]
                key_id = f"mistral_vision_{key_idx}"
                print(f"      -> [LLM Manager] Trying Mistral Vision Key {key_idx+1}/{max_m}...")
                self._rate_limit(key_id, min_interval=4.0)
                result = self._call_mistral_vision(key, prompt, base64_image, system)
                if result: return result
                print(f"      -> [LLM Manager] Mistral Vision Key {key_idx+1} failed.")
                
                
        print("      -> [LLM Manager] CRITICAL ERROR: All vision keys failed!")
        return None
        

    def _call_local_ollama(self, api_url, prompt, system, format, temperature, is_vision=False, base64_image=None):
        """Calls the Hugging Face ZeroGPU Gradio endpoint via gradio_client."""
        model = "qwen3.5:9b" if is_vision else "granite4.1:8b"
        
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}] if system else [{"role": "user", "content": prompt}]
        
        try:
            from gradio_client import Client
            import json
            
            clean_url = api_url.replace('/api/predict', '').rstrip('/')
            
            with self.lock:
                if clean_url not in self._hf_clients:
                    print(f"      -> [LLM Manager] Initializing Gradio Client for {clean_url}...")
                    self._hf_clients[clean_url] = Client(clean_url)
                client = self._hf_clients[clean_url]
            
            try:
                result = client.predict(
                    model,
                    json.dumps(messages),
                    base64_image if base64_image else "",
                    api_name="/chat"
                )
            except Exception as inner_e:
                if "Cannot find a function" in str(inner_e):
                    result = client.predict(
                        model,
                        json.dumps(messages),
                        base64_image if base64_image else "",
                        api_name="/predict"
                    )
                else:
                    raise inner_e
            return str(result).strip()
        except ImportError:
            print("      -> [LLM Manager] CRITICAL ERROR: gradio_client is not installed! Run `uv pip install gradio_client`")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Local Ollama Exception: {e}")
            return None

    def _call_ollama(self, prompt: str, system: Optional[str], format: str, temperature: float, *, url: Optional[str] = None, model: Optional[str] = None, timeout: int = 120) -> Optional[str]:
        url = (url or self.ollama_api_url).rstrip('/')
        if not url.endswith('/api/generate'): url += '/api/generate'
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
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("response")
            return None
        except Exception:
            return None

    def _call_github(self, api_key: Optional[str], prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        url = "https://models.inference.ai.azure.com/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}] if system else [{"role": "user", "content": prompt}]
        if format == "json":
            messages.append({"role": "user", "content": "You MUST return ONLY a valid JSON object. No other text."})
        payload = {"model": "Llama-3.3-70B-Instruct", "messages": messages, "temperature": temperature, "max_tokens": 4096}
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
            if resp.status_code == 200:
                text = resp.json()['choices'][0]['message']['content'].strip()
                return text
            print(f"      -> [LLM Manager] GitHub API Error {resp.status_code}: {resp.text[:200]}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] GitHub API Exception: {e}")
            return None

    def _call_nvidia(self, api_key: Optional[str], prompt: str, system: Optional[str], format: str, temperature: float, timeout: int = 120) -> Optional[str]:
        """Call NVIDIA NIM API with mistral-medium-3.5-128b."""
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}] if system else [{"role": "user", "content": prompt}]
        if format == "json":
            messages.append({"role": "user", "content": "You MUST return ONLY a valid JSON object. No other text."})
        payload = {"model": "mistralai/mistral-medium-3.5-128b", "messages": messages, "temperature": temperature, "max_tokens": 4096}
        if format == "json": payload["response_format"] = {"type": "json_object"}
            
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code == 200: return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] NVIDIA API Error {resp.status_code}: {resp.text[:200]}")
            if self._check_token_error(resp.text): return "ERROR_TOKEN_EXCEEDED"
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] NVIDIA API Exception: {e}")
            return None

    def _call_gemini(self, api_key: Optional[str], prompt: str, system: Optional[str], format: str, temperature: float, model_name: Optional[str] = None) -> Optional[str]:
        # Gemma 4 31B for text verification (default)
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
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200: return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"      -> [LLM Manager] Gemini API Error {resp.status_code}: {resp.text}")
            if self._check_token_error(resp.text): return "ERROR_TOKEN_EXCEEDED"
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Gemini API Exception: {e}")
            return None

    def _call_groq(self, api_key: Optional[str], prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
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
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] Groq API Error {resp.status_code}: {resp.text}")
            if self._check_token_error(resp.text): return "ERROR_TOKEN_EXCEEDED"
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Groq API Exception: {e}")
            return None
            


    def _call_mistral(self, api_key: Optional[str], prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
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
            resp = requests.post(url, headers=headers, json=payload, timeout=(30, 30))
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            print(f"      -> [LLM Manager] Mistral API Error {resp.status_code}: {resp.text}")
            if self._check_token_error(resp.text): return "ERROR_TOKEN_EXCEEDED"
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Mistral API Exception: {e}")
            return None

    def _call_gemini_vision(self, api_key: Optional[str], prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
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
            resp = requests.post(url, headers=headers, json=payload, timeout=(15, 30))
            if resp.status_code == 200: return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"      -> [LLM Manager] Gemini Vision Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e: 
            print(f"      -> [LLM Manager] Gemini Vision Exception: {e}")
            return None

    def _call_groq_vision(self, api_key: Optional[str], prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
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
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"Groq API Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Groq Error: {e}")
        return None

    def _call_mistral_vision(self, api_key: Optional[str], prompt: str, base64_image: str, system: Optional[str]) -> Optional[str]:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]})
        payload = {
            "model": "pixtral-12b-2409",
            "messages": messages,
            "temperature": 0.0
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"Mistral API Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Mistral Error: {e}")
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
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json().get("response")
            else:
                print(f"      -> [LLM Manager] Ollama Vision Error {resp.status_code}: {resp.text}")
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Ollama Vision Exception: {e}")
            return None





# Load .env variables
import os; load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ── Google AI Studio fallback helpers ───────────────────────────────────────────

def _load_google_ai():
    """Lazy-load google.generativeai; return None if not installed."""
    try:
        import google.generativeai as genai
        return genai
    except Exception:
        return None


def _google_ai_generate(prompt: str, model_name: str = "gemini-1.5-flash",
                        api_key: str = None, temperature: float = 0.0,
                        timeout: int = 120) -> Optional[str]:
    """Call Google AI Studio generative API. Returns raw text or None."""
    genai = _load_google_ai()
    if genai is None:
        print("      -> [LLM Manager] Google AI fallback not available: google-generativeai not installed.")
        return None
    if not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("      -> [LLM Manager] Google AI fallback not available: GOOGLE_API_KEY not set.")
        return None

    try:
        genai.configure(api_key=api_key, transport="rest")
        model = genai.GenerativeModel(model_name)
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            response_mime_type="application/json",
        )
        print(f"      -> [LLM Manager] Calling Google AI Studio ({model_name})...")
        resp = model.generate_content(
            prompt,
            generation_config=generation_config,
            request_options={"timeout": timeout},
        )
        if not resp or not resp.candidates:
            print("      -> [LLM Manager] Google AI returned no candidates.")
            return None
        return resp.text
    except Exception as e:
        print(f"      -> [LLM Manager] Google AI API Exception: {e}")
        return None


class LLMManagerOllama:
    """LLM manager with Ollama primary backend and Google AI Studio fallback.

    Text generation tries Ollama first, then a configured list of Ollama
    fallback models, and finally Google AI Studio (gemini-1.5-flash). Vision
    calls remain Ollama-only. Public method signatures are unchanged.
    """

    def __init__(self):
        # ── Ollama (primary LLM backend) ──
        # Cloud (ollama.com) when an API key is present, else local Ollama.
        self.ollama_api_key = os.environ.get("OLLAMA_API_KEY")
        default_url = "https://ollama.com" if self.ollama_api_key else "http://localhost:11434"
        raw_ollama_url = os.environ.get("OLLAMA_API_URL", default_url)

        # Normalize the URL so any secret shape resolves to the base host.
        if raw_ollama_url.endswith("/api/generate"):
            raw_ollama_url = raw_ollama_url[:-13]
        elif raw_ollama_url.endswith("/api"):
            raw_ollama_url = raw_ollama_url[:-4]
        self.ollama_api_url = raw_ollama_url

        # Text model: gemini-3-flash:cloud is the fast option for 20K-char page
        # prompts. gemini-3-flash:cloud is slower but can be used as a
        # fallback via OLLAMA_MODEL if nemotron misbehaves.
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "mistral-large-3:675b-cloud")

        # Ordered list of Ollama-hosted fallback models. If the primary model
        # fails (rate limit, timeout, model error), we try each in turn before
        # falling back to Google AI Studio.
        raw_fallbacks = os.environ.get("OLLAMA_FALLBACK_MODELS", "")
        if raw_fallbacks.strip():
            self.ollama_fallback_models = [m.strip() for m in raw_fallbacks.split(",") if m.strip()]
        else:
            self.ollama_fallback_models = [
                "gemma4:31b-cloud",
                "gemma4:26b-cloud",
                "mistral-large-3:675b-cloud",
            ]

        # Google AI Studio fallback (last resort)
        self.google_api_key = os.environ.get("GOOGLE_API_KEY")
        # Default to gemini-3-flash because that model is available and
        # within quota for this Google AI Studio key. Override via GOOGLE_MODEL.
        self.google_model = os.environ.get("GOOGLE_MODEL", "gemini-3-flash")
        default_url = "https://ollama.com" if self.ollama_api_key else "http://localhost:11434"
        raw_ollama_url = os.environ.get("OLLAMA_API_URL", default_url)

        # Normalize the URL so any secret shape resolves to the base host.
        if raw_ollama_url.endswith("/api/generate"):
            raw_ollama_url = raw_ollama_url[:-13]
        elif raw_ollama_url.endswith("/api"):
            raw_ollama_url = raw_ollama_url[:-4]
        self.ollama_api_url = raw_ollama_url

        # Text model: gemini-3-flash:cloud is the fast option for 20K-char page
        # prompts. gemini-3-flash:cloud is slower but can be used as a
        # fallback via OLLAMA_MODEL if nemotron misbehaves.
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "mistral-large-3:675b-cloud")

        # Vision model used for accuracy-critical OCR (fee tables, scanned PDFs).
        # Keep this on a strong vision model even if it's slower.
        self.ollama_vision_model = os.environ.get("OLLAMA_VISION_MODEL", "qwen3.5:cloud")

        # Lightweight navigation-only vision model for the action-decision rounds
        # (click/scroll/finish). This is called 3-6 times per hard course, strictly
        # serial, so a small fast model is a big wall-clock win. If it returns
        # unparseable JSON the caller can fall back to the main vision model.
        # Override via OLLAMA_NAV_VISION_MODEL env var.
        self.ollama_nav_vision_model = os.environ.get("OLLAMA_NAV_VISION_MODEL", "qwen3.5:cloud")

        # Track last call time per key to enforce rate limits
        self.last_call = {}
        self.lock = threading.Lock()

        # Vision call counter (serialized)
        self.vision_call_counter = 0
        self._vision_lock = threading.Lock()

        # Quota usage counters (Ollama Pro has 5h session / 7d weekly limits
        # billed by GPU-time). Printed at run end so you can see when you're
        # approaching the ceiling.
        self.text_call_count = 0
        self.vision_call_count = 0
        self._count_lock = threading.Lock()

        # ── Global concurrency cap ──
        # Ollama cloud queues requests over the plan's concurrency limit
        # (Free=1, Pro=3, Max=10) and rejects them once the queue fills,
        # which surfaces as "Read timed out" in CI. A shared semaphore lets
        # workers wait here for a slot instead of piling on Ollama's side.
        # Set OLLAMA_MAX_CONCURRENCY to match your plan.
        try:
            max_conc = int(os.environ.get("OLLAMA_MAX_CONCURRENCY", "3"))
        except ValueError:
            max_conc = 3
        if max_conc <= 0:
            max_conc = 3
        self._llm_semaphore = threading.Semaphore(max_conc)
        self.max_concurrency = max_conc

        # ── Shared HTTP session for connection reuse (keep-alive) ──
        # Every LLM call used to hit requests.post() with a fresh connection,
        # paying a TCP+TLS handshake (~100-300ms) to ollama.com each time. A
        # shared Session pools connections so repeated calls reuse the same
        # socket. urllib3's connection pool is thread-safe, so one Session is
        # fine across the worker threads. Pool sized to the concurrency cap so
        # every in-flight call can have its own connection.
        self._session = requests.Session()
        try:
            from requests.adapters import HTTPAdapter
            _adapter = HTTPAdapter(pool_connections=max_conc,
                                   pool_maxsize=max_conc,
                                   max_retries=0)
            self._session.mount("http://", _adapter)
            self._session.mount("https://", _adapter)
        except Exception:
            pass  # default adapter is fine if construction fails

        # Storage for the most recent Ollama error text (used by fallback logic)
        self._last_ollama_error = ""

        # ── Diagnostic logging ──
        fb_summary = ", ".join(self.ollama_fallback_models) if self.ollama_fallback_models else "none"
        print(f"[LLM Manager] Ollama primary | url={self.ollama_api_url} | "
              f"text_model={self.ollama_model} | fallback_models=[{fb_summary}] | "
              f"google_fallback={'enabled' if self.google_api_key else 'disabled'} | "
              f"auth={'bearer' if self.ollama_api_key else 'none'} | max_concurrency={max_conc}")
        if not self.ollama_api_url:
            print("[LLM Manager] [!] WARNING: OLLAMA_API_URL not set; targeting localhost:11434.")

        # Verify the Ollama endpoint + API key actually work before the run
        # starts when no fallback is configured. With fallbacks enabled we
        # only warn on failure so the run can try Google AI Studio if needed.
        if not self.ollama_fallback_models and not self.google_api_key:
            self._verify_ollama_access()
        else:
            self._verify_ollama_access(soft_fail=True)

    def _verify_ollama_access(self, attempts: int = 2, soft_fail: bool = False):
        """Verify the Ollama API key actually works via POST /api/generate.

        The public ``/api/tags`` and ``/api/version`` endpoints return 200 even
        with no/invalid auth, so they cannot confirm the key — they only prove
        the host is up. ``/api/generate`` is the only endpoint that enforces the
        bearer token on ollama.com cloud: 401 "Unauthorized" when the key is
        missing/invalid, 200 when it works. (``/api/ps`` also enforces auth but
        rejects the cloud key's scope, so it is unusable here.)

        We therefore send a tiny generation request: 200 => key valid and the
        run may proceed; 401/403 => key bad => halt immediately (sys.exit) so
        the run stops automatically instead of wasting itself on calls that
        would all return None. Retries once to ride out transient blips.
        """
        url = f"{self.ollama_api_url}/api/generate"
        headers = {"Content-Type": "application/json"}
        if self.ollama_api_key:
            headers["Authorization"] = f"Bearer {self.ollama_api_key}"
        payload = {
            "model": self.ollama_model,
            "prompt": "Reply with the single word: OK",
            "stream": False,
            "options": {"temperature": 0.0},
        }

        last_err = None
        for attempt in range(1, attempts + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 200:
                    data = resp.json() if resp.text else {}
                    # Key is valid (200 == authorized). The configured model may
                    # still report an error (e.g. wrong model name) — that is a
                    # config problem, not a key problem, so warn but do not halt.
                    if isinstance(data, dict) and data.get("error"):
                        print(f"[LLM Manager] [!] WARNING: Ollama key is valid but "
                              f"text model '{self.ollama_model}' returned an error: "
                              f"{str(data['error'])[:200]}")
                    print(f"[LLM Manager] [OK] Ollama API key verified "
                          f"(model '{self.ollama_model}' responded at "
                          f"{self.ollama_api_url}).")
                    return  # success — key works
                if resp.status_code in (401, 403):
                    last_err = (f"HTTP {resp.status_code} - key rejected "
                                f"({(resp.text or '')[:120]})")
                else:
                    last_err = f"HTTP {resp.status_code} {(resp.text or '')[:200]}"
            except Exception as e:
                last_err = str(e)

            if attempt < attempts:
                print(f"[LLM Manager] Ollama access check attempt {attempt}/{attempts} "
                      f"failed ({last_err}); retrying in 3s...")
                time.sleep(3)

        # All attempts failed.
        if soft_fail:
            print(f"[LLM Manager] [WARN] Ollama API key check failed: {last_err}. "
                  "Continuing because fallback models / Google AI Studio are configured.")
            return

        print(f"[LLM Manager] [FAIL] Ollama API key check FAILED: {last_err}")
        print(f"[LLM Manager] [FAIL] Endpoint: {url} | "
              f"key set: {'yes' if self.ollama_api_key else 'no'}")
        print("[LLM Manager] Halting: Ollama is the only LLM backend and the API "
              "key is missing/invalid or the endpoint is unreachable. Fix "
              "OLLAMA_API_URL / OLLAMA_API_KEY in your .env (or GitHub secret) "
              "and re-run.")
        sys.exit(1)

    def _rate_limit(self, key_identifier: str, min_interval: float = 4.29):
        """Enforces a minimum interval (in seconds) between API calls for a given key."""
        with self.lock:
            now = time.time()
            if key_identifier not in self.last_call:
                self.last_call[key_identifier] = 0.0

            elapsed = now - self.last_call[key_identifier]
            if elapsed < min_interval:
                wait_time = min_interval - elapsed
                print(f"      -> [Rate Limit] Sleeping for {wait_time:.1f}s for key {key_identifier}...")
                time.sleep(wait_time)
            self.last_call[key_identifier] = time.time()

    def _check_token_error(self, text: str) -> bool:
        err = text.lower()
        return "context" in err or "token" in err or "too large" in err or "exceeds" in err

    def _is_retryable_error(self, err_text: str) -> bool:
        """Return True if the Ollama error text indicates a transient failure."""
        if not err_text:
            return False
        text = err_text.lower()
        return any(s in text for s in [
            "timeout", "connection", "reset", "rate", "too many requests",
            "name resolution", "temporary", "503", "502", "504", "429",
        ])

    def generate(self, prompt: str, system: Optional[str] = None, format: str = "text",
                 temperature: float = 0.0, provider: str = "auto", worker_id: int = None,
                 model_name: str = None, timeout: int = None) -> Optional[str]:
        """Text generation with Ollama primary + Ollama/Google fallbacks.

        ``provider`` and ``model_name`` are accepted for backward compatibility
        but only ``model_name`` is honored for the Ollama primary attempt.
        """
        who = f"Worker {worker_id + 1} " if worker_id is not None else ""
        key_id = f"ollama_text_{worker_id if worker_id is not None else 0}"

        # Anti-burst throttle (per-worker). The global semaphore gates total concurrency.
        try:
            text_rate = float(os.environ.get("VERIFIER_TEXT_RATE_LIMIT", "0.2"))
        except ValueError:
            text_rate = 0.2
        if text_rate > 0:
            self._rate_limit(key_id, min_interval=text_rate)

        if timeout is None:
            try:
                timeout = int(os.environ.get("OLLAMA_TEXT_TIMEOUT", "180"))
            except ValueError:
                timeout = 180
        if timeout <= 0:
            timeout = 180

        # 1. Primary Ollama model
        models_to_try = [model_name or self.ollama_model]

        # 2. Ollama fallback models (only if this is the default text path)
        if not model_name:
            models_to_try.extend(self.ollama_fallback_models)

        with self._count_lock:
            self.text_call_count += 1

        last_err_text = ""
        for idx, model in enumerate(models_to_try):
            print(f"      -> [LLM Manager] {who}calling Ollama ({model})...")
            result = self._call_ollama(prompt, system, format, temperature,
                                       timeout=timeout, model=model)
            if result and result != "ERROR_TOKEN_EXCEEDED":
                return result
            if result == "ERROR_TOKEN_EXCEEDED":
                # Token errors won't be fixed by switching models on the same backend
                print(f"      -> [LLM Manager] {who}token limit hit on {model}; stopping.")
                return None
            err_text = self._last_ollama_error or ""
            last_err_text = err_text
            print(f"      -> [LLM Manager] {who}Ollama text call failed ({model}).")
            if not self._is_retryable_error(err_text):
                # Hard error (auth, bad model name, malformed request) — don't burn fallbacks
                break

        # 3. Last resort: Google AI Studio
        if self.google_api_key and _load_google_ai():
            print(f"      -> [LLM Manager] {who}Ollama exhausted; trying Google AI Studio fallback...")
            return _google_ai_generate(
                prompt,
                model_name=self.google_model,
                api_key=self.google_api_key,
                temperature=temperature,
                timeout=timeout,
            )

        print(f"      -> [LLM Manager] {who}All text generation attempts failed. Last Ollama error: {last_err_text[:160]}")
        return None

    def generate_with_image(self, prompt: str, base64_image: str,
                            system: Optional[str] = None, worker_id: int = None) -> Optional[str]:
        """Vision extraction via Ollama only (accuracy-critical OCR path)."""
        with self._vision_lock:
            current_call_idx = self.vision_call_counter
            self.vision_call_counter += 1

        print(f"      -> [LLM Manager] Vision call index: {current_call_idx} "
              f"-> Ollama ({self.ollama_vision_model})")
        self._rate_limit(f"ollama_vision_{current_call_idx}", min_interval=4.0)
        with self._count_lock:
            self.vision_call_count += 1
        result = self._call_ollama_vision(prompt, base64_image, system)
        if result:
            return result
        print("      -> [LLM Manager] CRITICAL ERROR: Ollama vision call failed!")
        return None

    def generate_nav_with_image(self, prompt: str, base64_image: str,
                                system: Optional[str] = None, worker_id: int = None) -> Optional[str]:
        """Fast navigation-only vision call (click/scroll/finish decisions)."""
        with self._vision_lock:
            current_call_idx = self.vision_call_counter
            self.vision_call_counter += 1

        print(f"      -> [LLM Manager] Nav vision call index: {current_call_idx} "
              f"-> Ollama ({self.ollama_nav_vision_model})")
        # Navigation rounds are strictly serial and low-stakes; use a tighter
        # rate limit so we don't unnecessarily pace a fast small model.
        self._rate_limit(f"ollama_nav_vision_{current_call_idx}", min_interval=2.0)
        with self._count_lock:
            self.vision_call_count += 1
        result = self._call_ollama_vision(prompt, base64_image, system,
                                          model=self.ollama_nav_vision_model,
                                          format="json")
        if result:
            return result
        print("      -> [LLM Manager] Nav vision call failed; caller should fall back.")
        return None

    def _call_ollama(self, prompt: str, system: Optional[str], format: str,
                    temperature: float, *, url: str = None, model: str = None,
                    timeout: int = 120) -> Optional[str]:
        if not url:
            url = f"{self.ollama_api_url}/api/generate"
        if not model:
            model = self.ollama_model
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192
            }
        }
        if system:
            payload["system"] = system
        if format == "json":
            payload["format"] = "json"

        self._llm_semaphore.acquire()
        try:
            headers = {"Content-Type": "application/json"}
            if self.ollama_api_key:
                headers["Authorization"] = f"Bearer {self.ollama_api_key}"
            resp = self._session.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                # Ollama may return an "error" field even with HTTP 200
                if data.get("error"):
                    err = str(data["error"])
                    print(f"      -> [LLM Manager] Ollama error: {err[:200]}")
                    self._last_ollama_error = err
                    if self._check_token_error(err):
                        return "ERROR_TOKEN_EXCEEDED"
                    return None
                self._last_ollama_error = ""
                return data.get("response")
            txt = resp.text or ""
            self._last_ollama_error = txt
            print(f"      -> [LLM Manager] Ollama API Error {resp.status_code}: {txt[:200]}")
            if self._check_token_error(txt):
                return "ERROR_TOKEN_EXCEEDED"
            return None
        except Exception as e:
            self._last_ollama_error = str(e)
            print(f"      -> [LLM Manager] Ollama API Exception: {e}")
            return None
        finally:
            self._llm_semaphore.release()

    def _call_ollama_vision(self, prompt: str, base64_image: str, system: Optional[str],
                            *, model: str = None, format: str = None) -> Optional[str]:
        url = f"{self.ollama_api_url}/api/generate"
        # Vision calls under concurrent worker load routinely exceed the old
        # 60s read timeout (see "Read timed out (read timeout=60)" in CI
        # logs). Give it real headroom and retry once on a transient
        # timeout/error so a single slow page doesn't drop extraction.
        # Overridable via OLLAMA_VISION_TIMEOUT.
        try:
            vision_timeout = int(os.environ.get("OLLAMA_VISION_TIMEOUT", "120"))
        except ValueError:
            vision_timeout = 120
        if vision_timeout <= 0:
            vision_timeout = 120

        if not model:
            model = self.ollama_vision_model

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "images": [base64_image],
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096
            }
        }
        if system:
            payload["system"] = system
        if format == "json":
            payload["format"] = "json"

        headers = {"Content-Type": "application/json"}
        if self.ollama_api_key:
            headers["Authorization"] = f"Bearer {self.ollama_api_key}"

        last_err = None
        for attempt in range(1, 3):  # original try + 1 retry
            try:
                # Hold the concurrency slot only for the in-flight HTTP call,
                # not the retry backoff — so the slot frees during the 3s sleep.
                self._llm_semaphore.acquire()
                try:
                    resp = self._session.post(url, json=payload, headers=headers, timeout=vision_timeout)
                finally:
                    self._llm_semaphore.release()
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("error"):
                        err = str(data["error"])
                        print(f"      -> [LLM Manager] Ollama Vision error: {err[:200]}")
                        return None
                    return data.get("response")
                # Non-200: retry once on transient server errors, else give up.
                last_err = f"HTTP {resp.status_code} {resp.text[:200]}"
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    print(f"      -> [LLM Manager] Ollama Vision {last_err}; retrying in 3s...")
                    time.sleep(3)
                    continue
                print(f"      -> [LLM Manager] Ollama Vision Error {resp.status_code}: {resp.text[:200]}")
                return None
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_err = str(e)
                if attempt < 2:
                    print(f"      -> [LLM Manager] Ollama Vision timeout/conn error ({str(e)[:120]}); retrying in 3s...")
                    time.sleep(3)
                    continue
                print(f"      -> [LLM Manager] Ollama Vision Exception: {e}")
                return None
            except Exception as e:
                print(f"      -> [LLM Manager] Ollama Vision Exception: {e}")
                return None
        print(f"      -> [LLM Manager] Ollama Vision failed after retry: {last_err}")
        return None

    def usage_summary(self) -> str:
        """One-line usage report for end-of-run logging."""
        with self._count_lock:
            t, v = self.text_call_count, self.vision_call_count
        total = t + v
        fb_summary = ", ".join(self.ollama_fallback_models) if self.ollama_fallback_models else "none"
        return (f"[LLM Manager] Usage: {total} calls ({t} text + {v} vision) | "
                f"max_concurrency={self.max_concurrency} | text_model={self.ollama_model} | "
                f"fallbacks=[{fb_summary}] | google_fallback={'enabled' if self.google_api_key else 'disabled'}")



_instance = None

def get_llm_manager():
    global _instance
    if _instance is None:
        import os
        backend = os.environ.get("LLM_BACKEND", "api").strip().lower()
        if backend == "ollama":
            _instance = LLMManagerOllama()
        else:
            _instance = LLMManagerAPI()
    return _instance
