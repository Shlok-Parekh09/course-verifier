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
        # Cloud/remote Ollama - must be explicitly set via env vars.
        # .strip() guards against trailing newlines/whitespace that secret
        # stores (GitHub Actions, .env pastes) sometimes append, which
        # otherwise corrupt the request URL (e.g. /api/generate%0A/api/generate).
        _oc_url = os.environ.get("OLLAMA_API_URL")
        self.cloud_ollama_url = _oc_url.strip() if _oc_url else None
        _oc_model = os.environ.get("OLLAMA_MODEL")
        self.cloud_ollama_model = _oc_model.strip() if _oc_model else None

        # Cloud Ollama (ollama.com) is the ONLY LLM backend used. There is no
        # local Ollama fallback: in environments without one (Colab/CI/laptops
        # without a local server) it just produced "Connection refused" noise
        # and wasted a retry round before returning None. The cloud endpoint is
        # required to be set via OLLAMA_API_URL.
        #
        # Normalize to just scheme://host so the call endpoint is ALWAYS
        # "<host>/api/generate", no matter which form the env/secret takes:
        #   https://ollama.com                        -> https://ollama.com/api/generate
        #   https://ollama.com/api                    -> https://ollama.com/api/generate
        #   https://ollama.com/api/generate           -> https://ollama.com/api/generate
        #   https://ollama.com/api/generate.          -> https://ollama.com/api/generate
        #   https://ollama.com/api/generate./api/...  -> https://ollama.com/api/generate
        # String-suffix stripping was not robust: it produced "/api/api/generate"
        # and "/api/generate./api/generate" 404s on different secret shapes.
        # Parsing with urlsplit and discarding the path is the only form that
        # survives every variant a secret store can hand us.
        raw_ollama_url = os.environ.get("OLLAMA_API_URL", "").strip()
        if raw_ollama_url and "://" not in raw_ollama_url:
            raw_ollama_url = "https://" + raw_ollama_url
        try:
            from urllib.parse import urlsplit
            parts = urlsplit(raw_ollama_url)
            if parts.scheme and parts.netloc:
                self.ollama_api_url = f"{parts.scheme}://{parts.netloc}"
            else:
                self.ollama_api_url = raw_ollama_url.rstrip("/")
        except Exception:
            self.ollama_api_url = raw_ollama_url.rstrip("/")
        self.ollama_model   = os.environ.get("OLLAMA_MODEL", "llama3").strip()
        self.ollama_vision_model = os.environ.get("OLLAMA_VISION_MODEL", "gemma4:31b-cloud").strip()

        # Track last call time per provider to enforce rate limits
        # Track last call time per key to enforce rate limits individually
        self.last_call = {}
        self.lock = threading.Lock()

        # Tunable Ollama timeouts / retries (env-overridable). Defaults raised from
        # 30s/45s so genuinely-slow-but-working ollama.com responses complete instead
        # of timing out into the error path (which yields cost_match=False). The
        # failover chain (Gemini -> OpenRouter -> NVIDIA) still kicks in once Ollama
        # gives up, so worst case is bounded.
        self.ollama_timeout = int(os.environ.get("OLLAMA_TIMEOUT", "45"))
        self.ollama_vision_timeout = int(os.environ.get("OLLAMA_VISION_TIMEOUT", "75"))
        self.ollama_max_attempts = int(os.environ.get("OLLAMA_MAX_ATTEMPTS", "3"))

        # One-time diagnostic: show which failover providers actually have keys.
        # In CI this reveals whether OLLAMA-only failures can fall back at all
        # (e.g. if GEMINI_KEY_1 / OPENROUTER_KEY_1 secrets are unset, every Ollama
        # timeout goes straight to None -> cost_match=False).
        print(f"      -> [LLM Manager] Providers configured — Ollama: "
              f"{'yes' if self.ollama_api_url else 'NO (OLLAMA_API_URL unset)'}, "
              f"Gemini keys: {len(self.gemini_keys)}, "
              f"OpenRouter keys: {len(self.openrouter_keys)}, "
              f"NVIDIA keys: {len(self.nvidia_keys)} | "
              f"timeouts text={self.ollama_timeout}s vision={self.ollama_vision_timeout}s "
              f"attempts={self.ollama_max_attempts}")

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

    def generate(self, prompt: str, system: Optional[str] = None, format: str = "text", temperature: float = 0.0, provider: str = "auto", worker_id: int = None) -> Optional[str]:
        # Text Generation: Cloud Ollama -> Gemini -> OpenRouter -> NVIDIA -> Local Ollama

        # --- Tier 1: Configured (cloud/remote) Ollama ---
        if provider in ["auto", "ollama"]:
            try:
                print(f"      -> [LLM Manager] Trying Ollama ({self.ollama_api_url} | {self.ollama_model})...")
                res = self._call_ollama(prompt, system, format, 0.0, url=self.ollama_api_url + "/api/generate", model=self.ollama_model)
                if res: return res
                print("      -> [LLM Manager] Ollama failed or unavailable. Failing over to other APIs...")
            except Exception as e:
                print(f"      -> [LLM Manager] Ollama crashed ({e}). Failing over...")

        if worker_id is not None:
            # DEDICATED KEY LOGIC for Multithreading
            # Chain: Gemini → OpenRouter → NVIDIA (with 2 keys per provider)

            if self.gemini_keys and provider in ["auto", "gemini"]:
                for idx in self._get_key_sequence(worker_id, len(self.gemini_keys)):
                    g_key = self.gemini_keys[idx]
                    key_id = f"gemini_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying Gemini Key {idx+1}...")
                    self._rate_limit(key_id)
                    res = self._call_gemini(g_key, prompt, system, format, 0.0)
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
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s OpenRouter keys failed. Failing over to NVIDIA...")

            if self.nvidia_keys and provider in ["auto", "nvidia"]:
                for idx in self._get_key_sequence(worker_id, len(self.nvidia_keys)):
                    n_key = self.nvidia_keys[idx]
                    key_id = f"nvidia_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying NVIDIA Key {idx+1}...")
                    self._rate_limit(key_id, min_interval=1.0)
                    res = self._call_nvidia(n_key, prompt, system, format, 0.0)
                    if res: return res
                print(f"      -> [LLM Manager] Worker {worker_id+1}'s NVIDIA keys failed.")

            return None

        # FALLBACK SEQUENTIAL LOGIC (If worker_id is not provided)
        # Provider 1: GEMINI
        for idx, key in enumerate(self.gemini_keys):
            print(f"      -> [LLM Manager] Trying Gemini Key {idx+1}/{len(self.gemini_keys)}...")
            self._rate_limit(f"gemini_{idx}")
            result = self._call_gemini(key, prompt, system, format, 0.0)
            if result: return result
            print(f"      -> [LLM Manager] Gemini Key {idx+1} failed. Failing over...")

        # Provider 2: OPENROUTER
        for idx, key in enumerate(self.openrouter_keys):
            print(f"      -> [LLM Manager] Trying OpenRouter Key {idx+1}/{len(self.openrouter_keys)}...")
            self._rate_limit(f"openrouter_{idx}", min_interval=1.0)
            result = self._call_openrouter(key, prompt, system, format, 0.0)
            if result: return result
            print(f"      -> [LLM Manager] OpenRouter Key {idx+1} failed. Failing over...")

        # Provider 3: NVIDIA
        for idx, key in enumerate(self.nvidia_keys):
            print(f"      -> [LLM Manager] Trying NVIDIA Key {idx+1}/{len(self.nvidia_keys)}...")
            self._rate_limit(f"nvidia_{idx}", min_interval=1.0)
            result = self._call_nvidia(key, prompt, system, format, 0.0)
            if result: return result
            print(f"      -> [LLM Manager] NVIDIA Key {idx+1} failed. Failing over...")

        print("      -> [LLM Manager] CRITICAL ERROR: All configured LLM providers failed!")
        return None

    def generate_with_image(self, prompt: str, base64_image: str, system: Optional[str] = None, worker_id: int = None) -> Optional[str]:
        """Method for Vision extraction using Ollama, Groq, Mistral, and SambaNova"""
        
        # 0. OLLAMA VISION PRIMARY
        try:
            print(f"      -> [LLM Manager] Trying Ollama Vision ({self.ollama_api_url} | {self.ollama_vision_model})...")
            res = self._call_ollama_vision(prompt, base64_image, system)
            if res: return res
            print("      -> [LLM Manager] Ollama Vision failed or unavailable. Failing over...")
        except Exception as e:
            print(f"      -> [LLM Manager] Ollama Vision error: {e}. Failing over...")

        if worker_id is not None:
            # DEDICATED KEY LOGIC for Multithreading Vision
            # Chain: Groq → Mistral → SambaNova (with 2 keys per provider)
            
            if self.groq_keys:
                for idx in self._get_key_sequence(worker_id, len(self.groq_keys)):
                    g_key = self.groq_keys[idx]
                    key_id = f"groq_vision_{idx}"
                    print(f"      -> [LLM Manager] Worker {worker_id+1} trying Groq Vision Key {idx+1} (Llama 4 Scout)...")
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
                print(f"      -> [LLM Manager] Trying Groq Vision Key {idx+1}/{len(self.groq_keys)} (Llama 4 Scout)...")
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
        if not self.ollama_api_url:
            print("      -> [LLM Manager] OLLAMA_API_URL is not set. Cannot call cloud Ollama.")
            return None
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

        # Cloud Ollama providers (RunPod, Together, Groq, etc.) often require an API key
        headers = {"Content-Type": "application/json"}
        ollama_key = os.environ.get("OLLAMA_API_KEY")
        if ollama_key:
            headers["Authorization"] = f"Bearer {ollama_key}"

        # Retry transient failures (rate limit 429, 5xx, timeouts, AND connection
        # errors) with exponential backoff. Previously a transient ConnectionError
        # (e.g. "Max retries exceeded" / "Connection refused" during a network
        # blip) hit the generic except and returned None immediately, killing the
        # whole verification for that course. Connection errors are now retried
        # too, since they are overwhelmingly transient.
        #
        # Tuned for SPEED: a 90s timeout x 5 attempts used to burn up to 7.5 min
        # on a single slow/overloaded model call before returning None. The model
        # normally replies in <20s; if it hasn't in 30s it is overloaded and
        # retrying many more times just wastes wall-clock. Defaults are now env-
        # tunable (OLLAMA_TIMEOUT / OLLAMA_MAX_ATTEMPTS) and raised to 45s x 3 so
        # slow-but-working ollama.com responses complete; the Gemini/OpenRouter
        # failover chain catches the rest.
        max_attempts = self.ollama_max_attempts
        for attempt in range(max_attempts):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.ollama_timeout)
                if resp.status_code == 200:
                    return resp.json().get("response")
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2 ** attempt, 4)
                    print(f"      -> [LLM Manager] Ollama HTTP {resp.status_code}; retrying in {wait}s (attempt {attempt+1}/{max_attempts})...")
                    time.sleep(wait)
                    continue
                # Non-retryable (e.g. 401 bad key, 404 bad model). Surface the real error.
                print(f"      -> [LLM Manager] Ollama HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError) as e:
                wait = min(2 ** attempt, 4)
                last_err = str(e).split('\n')[0][:120]
                print(f"      -> [LLM Manager] Ollama transient error ({last_err}); retrying in {wait}s (attempt {attempt+1}/{max_attempts})...")
                time.sleep(wait)
            except Exception as e:
                print(f"      -> [LLM Manager] Ollama request error: {e}")
                return None
        print(f"      -> [LLM Manager] Ollama exhausted {max_attempts} attempts. Giving up.")
        return None

    def _call_openrouter(self, api_key: str, prompt: str, system: Optional[str], format: str, temperature: float) -> Optional[str]:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = []
        if system: messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {"model": "nvidia/nemotron-3-super-120b-a12b:free", "messages": messages, "temperature": temperature}
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
        
        payload = {"model": "meta/llama-3.3-70b-instruct", "messages": messages, "temperature": temperature, "max_tokens": 4096}
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
        # Gemma 4 31B for text verification (user requested exact string)
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
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
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
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
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

        # Cloud Ollama (ollama.com) requires a Bearer API key. This was missing,
        # so every vision call returned 401 Unauthorized even with a valid key.
        headers = {"Content-Type": "application/json"}
        ollama_key = os.environ.get("OLLAMA_API_KEY")
        if ollama_key:
            headers["Authorization"] = f"Bearer {ollama_key}"

        # Vision calls are heavier (image payload) and prone to timeouts/rate
        # limits; retry transient failures (including connection errors) with
        # backoff. Tuned for speed: defaults env-tunable (OLLAMA_VISION_TIMEOUT /
        # OLLAMA_MAX_ATTEMPTS), 75s x 3 attempts.
        max_attempts = self.ollama_max_attempts
        for attempt in range(max_attempts):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.ollama_vision_timeout)
                if resp.status_code == 200:
                    return resp.json().get("response")
                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = min(2 ** attempt, 4)
                    print(f"      -> [LLM Manager] Ollama Vision HTTP {resp.status_code}; retrying in {wait}s (attempt {attempt+1}/{max_attempts})...")
                    time.sleep(wait)
                    continue
                print(f"      -> [LLM Manager] Ollama Vision Error {resp.status_code}: {resp.text[:200]}")
                return None
            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError) as e:
                wait = min(2 ** attempt, 4)
                last_err = str(e).split('\n')[0][:120]
                print(f"      -> [LLM Manager] Ollama Vision transient error ({last_err}); retrying in {wait}s (attempt {attempt+1}/{max_attempts})...")
                time.sleep(wait)
            except Exception as e:
                print(f"      -> [LLM Manager] Ollama Vision Exception: {e}")
                return None
        print(f"      -> [LLM Manager] Ollama Vision exhausted {max_attempts} attempts. Giving up.")
        return None

# Global Singleton for easy import
_llm_manager = None
def get_llm_manager():
    global _llm_manager
    if _llm_manager is None:
        _llm_manager = LLMManager()
    return _llm_manager
