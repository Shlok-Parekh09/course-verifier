import os
import sys
import json
import requests
import time
import threading
from typing import Optional
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

class LLMManager:
    """LLM manager routed exclusively through the Ollama API.

    Both text generation (``generate``) and vision extraction
    (``generate_with_image``) call Ollama only — the previous multi-provider
    failover (Mistral/Groq/SambaNova/OpenRouter/NVIDIA/Gemini/Puter) has been
    removed. The public method signatures are unchanged so existing callers in
    ``autonomous_course_verifier.py`` keep working; provider/model_name
    parameters are accepted for compatibility but ignored (single backend).
    """

    def __init__(self):
        # ── Ollama (the only LLM backend) ──
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

        # nemotron-3-nano:30b is the sweet spot for this verifier — 20K-char
        # page prompts in ~11–14s with valid JSON. See memory: ollama-cloud-model-choice.
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "nemotron-3-nano:30b")
        self.ollama_vision_model = os.environ.get("OLLAMA_VISION_MODEL", "gemma4:31b-cloud")

        # Track last call time per key to enforce rate limits
        self.last_call = {}
        self.lock = threading.Lock()

        # Vision call counter (serialized)
        self.vision_call_counter = 0
        self._vision_lock = threading.Lock()

        # ── Diagnostic logging ──
        print(f"[LLM Manager] Ollama-only mode | url={self.ollama_api_url} | "
              f"text_model={self.ollama_model} | vision_model={self.ollama_vision_model} | "
              f"auth={'bearer' if self.ollama_api_key else 'none'}")
        if not self.ollama_api_url:
            print("[LLM Manager] [!] WARNING: OLLAMA_API_URL not set; targeting localhost:11434.")

        # Verify the Ollama endpoint + API key actually work before the run
        # starts. If they don't, halt immediately — every subsequent LLM call
        # would silently return None and waste the entire verification run.
        self._verify_ollama_access()

    def _verify_ollama_access(self, attempts: int = 2):
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

        # All attempts failed — stop the run.
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

    def generate(self, prompt: str, system: Optional[str] = None, format: str = "text",
                 temperature: float = 0.0, provider: str = "auto", worker_id: int = None,
                 model_name: str = None, timeout: int = 120) -> Optional[str]:
        """Text generation via Ollama only.

        ``provider`` and ``model_name`` are accepted for backward compatibility
        with existing call sites but are ignored — every call routes to Ollama.
        """
        who = f"Worker {worker_id + 1} " if worker_id is not None else ""
        key_id = f"ollama_text_{worker_id if worker_id is not None else 0}"
        model = model_name or self.ollama_model
        print(f"      -> [LLM Manager] {who}calling Ollama ({model})...")
        self._rate_limit(key_id, min_interval=1.0)
        result = self._call_ollama(prompt, system, format, temperature,
                                   timeout=timeout, model=model)
        if result:
            return result
        print(f"      -> [LLM Manager] {who}Ollama text call failed.")
        return None

    def generate_with_image(self, prompt: str, base64_image: str,
                            system: Optional[str] = None, worker_id: int = None) -> Optional[str]:
        """Vision extraction via Ollama only."""
        with self._vision_lock:
            current_call_idx = self.vision_call_counter
            self.vision_call_counter += 1

        print(f"      -> [LLM Manager] Vision call index: {current_call_idx} "
              f"-> Ollama ({self.ollama_vision_model})")
        self._rate_limit(f"ollama_vision_{current_call_idx}", min_interval=4.0)
        result = self._call_ollama_vision(prompt, base64_image, system)
        if result:
            return result
        print("      -> [LLM Manager] CRITICAL ERROR: Ollama vision call failed!")
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
                "temperature": temperature
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
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                # Ollama may return an "error" field even with HTTP 200
                if data.get("error"):
                    err = str(data["error"])
                    print(f"      -> [LLM Manager] Ollama error: {err[:200]}")
                    if self._check_token_error(err):
                        return "ERROR_TOKEN_EXCEEDED"
                    return None
                return data.get("response")
            txt = resp.text or ""
            print(f"      -> [LLM Manager] Ollama API Error {resp.status_code}: {txt[:200]}")
            if self._check_token_error(txt):
                return "ERROR_TOKEN_EXCEEDED"
            return None
        except Exception as e:
            print(f"      -> [LLM Manager] Ollama API Exception: {e}")
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
                data = resp.json()
                if data.get("error"):
                    err = str(data["error"])
                    print(f"      -> [LLM Manager] Ollama Vision error: {err[:200]}")
                    return None
                return data.get("response")
            print(f"      -> [LLM Manager] Ollama Vision Error {resp.status_code}: {resp.text[:200]}")
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