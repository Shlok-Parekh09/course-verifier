#!/usr/bin/env python3
"""
api_checker.py  -  Comprehensive API Health Checker
===================================================
Verifies every internal Flask route and every external LLM / service
API used by the course-verifier stack.  Run it stand-alone:

    python api_checker.py

It will exit with code 0 if everything passes, or 1 if anything fails.
"""

import os
import sys
import io
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
#  Load .env before anything else
# ---------------------------------------------------------------------------
load_dotenv()

# Windows terminals often choke on Unicode box-drawing; force UTF-8 when possible
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
#  Colour helpers (no external deps)
# ---------------------------------------------------------------------------
class _C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def _ok(label: str, elapsed: float) -> str:
    return f"{_C.GREEN}[PASS]{_C.RESET} {_C.BOLD}{label}{_C.RESET}  ({elapsed:.2f}s)"

def _fail(label: str, elapsed: float, msg: str) -> str:
    return f"{_C.RED}[FAIL]{_C.RESET} {_C.BOLD}{label}{_C.RESET}  ({elapsed:.2f}s)  -> {msg}"

def _skip(label: str, reason: str) -> str:
    return f"{_C.YELLOW}[SKIP]{_C.RESET} {_C.BOLD}{label}{_C.RESET}  -> {reason}"

def _info(text: str) -> str:
    return f"{_C.CYAN}[INFO]{_C.RESET} {text}"

# ---------------------------------------------------------------------------
#  Result accumulator
# ---------------------------------------------------------------------------
class CheckResult:
    def __init__(self, name: str, ok: bool, elapsed: float, msg: str = "", skipped: bool = False):
        self.name = name
        self.ok = ok
        self.elapsed = elapsed
        self.msg = msg
        self.skipped = skipped

# ---------------------------------------------------------------------------
#  Internal Flask checks (via test_client so no port juggling needed)
# ---------------------------------------------------------------------------
def _check_internal() -> List[CheckResult]:
    results: List[CheckResult] = []
    t0 = time.time()

    # Import here so that missing deps don’t crash the whole script early
    try:
        from dashboard import app  # type: ignore
    except Exception as exc:
        results.append(CheckResult("Import dashboard.app", False, time.time() - t0, str(exc)))
        return results

    client = app.test_client()

    # ---- GET / ----
    s = time.time()
    try:
        rv = client.get("/")
        if rv.status_code == 200:
            results.append(CheckResult("GET /", True, time.time() - s))
        else:
            results.append(CheckResult("GET /", False, time.time() - s, f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("GET /", False, time.time() - s, str(exc)))

    # ---- GET /api/courses ----
    s = time.time()
    try:
        rv = client.get("/api/courses")
        if rv.status_code == 200:
            data = rv.get_json()
            if isinstance(data, dict) and "courses" in data:
                results.append(CheckResult("GET /api/courses", True, time.time() - s,
                                           f"{len(data['courses'])} courses"))
            else:
                results.append(CheckResult("GET /api/courses", False, time.time() - s, "missing 'courses' key"))
        else:
            results.append(CheckResult("GET /api/courses", False, time.time() - s, f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("GET /api/courses", False, time.time() - s, str(exc)))

    # ---- GET /api/courses.json ----
    s = time.time()
    try:
        rv = client.get("/api/courses.json")
        ok = rv.status_code == 200 and isinstance(rv.get_json(), dict)
        results.append(CheckResult("GET /api/courses.json", ok, time.time() - s,
                                   "" if ok else f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("GET /api/courses.json", False, time.time() - s, str(exc)))

    # ---- GET /api/data ----
    s = time.time()
    try:
        rv = client.get("/api/data")
        if rv.status_code == 200:
            data = rv.get_json()
            if isinstance(data, dict) and "stats" in data:
                results.append(CheckResult("GET /api/data", True, time.time() - s,
                                           f"stats={json.dumps(data['stats'])[:60]}..."))
            else:
                results.append(CheckResult("GET /api/data", False, time.time() - s, "missing 'stats' key"))
        else:
            results.append(CheckResult("GET /api/data", False, time.time() - s, f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("GET /api/data", False, time.time() - s, str(exc)))

    # ---- GET /api/data.json ----
    s = time.time()
    try:
        rv = client.get("/api/data.json")
        ok = rv.status_code == 200 and isinstance(rv.get_json(), dict)
        results.append(CheckResult("GET /api/data.json", ok, time.time() - s,
                                   "" if ok else f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("GET /api/data.json", False, time.time() - s, str(exc)))

    # ---- GET /api/analytics ----
    s = time.time()
    try:
        rv = client.get("/api/analytics")
        if rv.status_code == 200:
            data = rv.get_json()
            ok = isinstance(data, dict) and "data" in data
            results.append(CheckResult("GET /api/analytics", ok, time.time() - s,
                                       "" if ok else "missing 'data' key"))
        else:
            results.append(CheckResult("GET /api/analytics", False, time.time() - s, f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("GET /api/analytics", False, time.time() - s, str(exc)))

    # ---- GET /api/analytics.json ----
    s = time.time()
    try:
        rv = client.get("/api/analytics.json")
        ok = rv.status_code == 200 and isinstance(rv.get_json(), dict)
        results.append(CheckResult("GET /api/analytics.json", ok, time.time() - s,
                                   "" if ok else f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("GET /api/analytics.json", False, time.time() - s, str(exc)))

    # ---- DELETE /api/course/<id>  (safe: non-existent ID) ----
    s = time.time()
    try:
        rv = client.delete("/api/course/999999")
        # We expect a 404; a 404 proves routing + handler are alive.
        if rv.status_code == 404:
            results.append(CheckResult("DELETE /api/course/:id (404)", True, time.time() - s, "route reachable"))
        elif rv.status_code == 200:
            results.append(CheckResult("DELETE /api/course/:id", False, time.time() - s,
                                       "unexpectedly deleted a real course"))
        else:
            results.append(CheckResult("DELETE /api/course/:id", False, time.time() - s,
                                       f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("DELETE /api/course/:id", False, time.time() - s, str(exc)))

    # ---- POST /api/upload  (empty multipart, should succeed with 0 updates) ----
    s = time.time()
    try:
        rv = client.post("/api/upload", data={"files[]": (io.BytesIO(b""), "")},
                         content_type="multipart/form-data")
        # The handler skips empty filenames, so 200 with updates=0 is expected.
        if rv.status_code == 200:
            data = rv.get_json()
            ok = isinstance(data, dict) and data.get("status") == "success"
            results.append(CheckResult("POST /api/upload", ok, time.time() - s,
                                       f"updates={data.get('updates', '?')}" if ok else "bad payload"))
        else:
            results.append(CheckResult("POST /api/upload", False, time.time() - s, f"HTTP {rv.status_code}"))
    except Exception as exc:
        results.append(CheckResult("POST /api/upload", False, time.time() - s, str(exc)))

    return results

# ---------------------------------------------------------------------------
#  External LLM / provider checks  (cheap, token-friendly probes)
# ---------------------------------------------------------------------------
def _probe_openrouter(keys: List[str]) -> List[CheckResult]:
    results: List[CheckResult] = []
    url = "https://openrouter.ai/api/v1/models"
    for idx, key in enumerate(keys[:2]):          # cap at 2 keys to keep it fast
        name = f"OpenRouter Key {idx+1}"
        s = time.time()
        try:
            rv = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=15)
            ok = rv.status_code == 200 and "data" in rv.json()
            results.append(CheckResult(name, ok, time.time() - s,
                                       f"HTTP {rv.status_code}" if not ok else f"{len(rv.json().get('data', []))} models"))
        except Exception as exc:
            results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

def _probe_gemini(keys: List[str]) -> List[CheckResult]:
    results: List[CheckResult] = []
    for idx, key in enumerate(keys[:2]):
        name = f"Gemini Key {idx+1}"
        s = time.time()
        try:
            rv = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=1",
                              timeout=15)
            ok = rv.status_code == 200 and "models" in rv.json()
            results.append(CheckResult(name, ok, time.time() - s,
                                       f"HTTP {rv.status_code}" if not ok else "models reachable"))
        except Exception as exc:
            results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

def _probe_nvidia(keys: List[str]) -> List[CheckResult]:
    results: List[CheckResult] = []
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    for idx, key in enumerate(keys[:1]):            # Nvidia is $$$, only 1 key, tiny payload
        name = f"NVIDIA NIM Key {idx+1}"
        s = time.time()
        try:
            payload = {
                "model": "meta/llama-3.3-70b-instruct",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
                "temperature": 0.0
            }
            rv = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                json=payload, timeout=30)
            # 200 means working; 401/403 means key issue; 429 means rate limit (still "reachable")
            ok = rv.status_code in (200, 429)
            results.append(CheckResult(name, ok, time.time() - s,
                                       f"HTTP {rv.status_code}" if not ok else ("OK" if rv.status_code == 200 else "rate-limited")))
        except Exception as exc:
            results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

def _probe_groq(keys: List[str]) -> List[CheckResult]:
    results: List[CheckResult] = []
    url = "https://api.groq.com/openai/v1/models"
    for idx, key in enumerate(keys[:2]):
        name = f"Groq Key {idx+1}"
        s = time.time()
        try:
            rv = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=15)
            ok = rv.status_code == 200 and isinstance(rv.json(), dict)
            results.append(CheckResult(name, ok, time.time() - s,
                                       f"HTTP {rv.status_code}" if not ok else "models reachable"))
        except Exception as exc:
            results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

def _probe_mistral(keys: List[str]) -> List[CheckResult]:
    results: List[CheckResult] = []
    url = "https://api.mistral.ai/v1/models"
    for idx, key in enumerate(keys[:2]):
        name = f"Mistral Key {idx+1}"
        s = time.time()
        try:
            rv = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=15)
            ok = rv.status_code == 200 and isinstance(rv.json(), dict)
            results.append(CheckResult(name, ok, time.time() - s,
                                       f"HTTP {rv.status_code}" if not ok else "models reachable"))
        except Exception as exc:
            results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

def _probe_sambanova(keys: List[str]) -> List[CheckResult]:
    results: List[CheckResult] = []
    url = "https://api.sambanova.ai/v1/chat/completions"
    for idx, key in enumerate(keys[:1]):
        name = f"SambaNova Key {idx+1}"
        s = time.time()
        try:
            payload = {
                "model": "Meta-Llama-3.1-70B-Instruct",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 1,
                "temperature": 0.0
            }
            rv = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                json=payload, timeout=30)
            ok = rv.status_code in (200, 429)
            results.append(CheckResult(name, ok, time.time() - s,
                                       f"HTTP {rv.status_code}" if not ok else ("OK" if rv.status_code == 200 else "rate-limited")))
        except Exception as exc:
            results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

def _probe_ollama() -> List[CheckResult]:
    results: List[CheckResult] = []
    base = os.environ.get("OLLAMA_API_URL", "http://localhost:11434").rstrip("/")
    if base.endswith("/api/generate"):
        base = base[:-13]
    url = f"{base}/api/tags"
    name = "Ollama (local)"
    s = time.time()
    try:
        rv = requests.get(url, timeout=5)
        ok = rv.status_code == 200 and "models" in rv.json()
        results.append(CheckResult(name, ok, time.time() - s,
                                   f"HTTP {rv.status_code}" if not ok else f"{len(rv.json().get('models', []))} models"))
    except Exception as exc:
        results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

def _check_llm() -> List[CheckResult]:
    results: List[CheckResult] = []

    # ---- Collect keys exactly like llm_manager.py does ----
    openrouter_keys = [os.environ.get(f"OPENROUTER_KEY_{i}") for i in range(1, 7) if os.environ.get(f"OPENROUTER_KEY_{i}")]
    gemini_keys     = [os.environ.get(f"GEMINI_KEY_{i}")     for i in range(1, 7) if os.environ.get(f"GEMINI_KEY_{i}")]
    nvidia_keys     = [os.environ.get(f"NVIDIA_KEY_{i}")     for i in range(1, 7) if os.environ.get(f"NVIDIA_KEY_{i}")]
    groq_keys       = ([os.environ.get(f"GROQ_API_KEY_{i}")   for i in range(1, 7) if os.environ.get(f"GROQ_API_KEY_{i}")]
                       or ([os.environ.get("GROQ_API_KEY")] if os.environ.get("GROQ_API_KEY") else []))
    mistral_keys    = ([os.environ.get(f"MISTRAL_API_KEY_{i}") for i in range(1, 7) if os.environ.get(f"MISTRAL_API_KEY_{i}")]
                       or ([os.environ.get("MISTRAL_API_KEY")] if os.environ.get("MISTRAL_API_KEY") else []))
    sambanova_keys  = ([os.environ.get(f"SAMBANOVA_API_KEY_{i}") for i in range(1, 7) if os.environ.get(f"SAMBANOVA_API_KEY_{i}")]
                       or ([os.environ.get("SAMBANOVA_API_KEY")] if os.environ.get("SAMBANOVA_API_KEY") else []))

    if openrouter_keys:
        results.extend(_probe_openrouter(openrouter_keys))
    else:
        results.append(CheckResult("OpenRouter", False, 0.0, "No OPENROUTER_KEY_* in .env", skipped=True))

    if gemini_keys:
        results.extend(_probe_gemini(gemini_keys))
    else:
        results.append(CheckResult("Gemini", False, 0.0, "No GEMINI_KEY_* in .env", skipped=True))

    if nvidia_keys:
        results.extend(_probe_nvidia(nvidia_keys))
    else:
        results.append(CheckResult("NVIDIA NIM", False, 0.0, "No NVIDIA_KEY_* in .env", skipped=True))

    if groq_keys:
        results.extend(_probe_groq(groq_keys))
    else:
        results.append(CheckResult("Groq", False, 0.0, "No GROQ_API_KEY_* in .env", skipped=True))

    if mistral_keys:
        results.extend(_probe_mistral(mistral_keys))
    else:
        results.append(CheckResult("Mistral", False, 0.0, "No MISTRAL_API_KEY_* in .env", skipped=True))

    if sambanova_keys:
        results.extend(_probe_sambanova(sambanova_keys))
    else:
        results.append(CheckResult("SambaNova", False, 0.0, "No SAMBANOVA_API_KEY_* in .env", skipped=True))

    results.extend(_probe_ollama())

    return results

# ---------------------------------------------------------------------------
#  Firebase / Firestore connectivity
# ---------------------------------------------------------------------------
def _check_firebase() -> List[CheckResult]:
    results: List[CheckResult] = []
    s = time.time()
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if os.path.exists("serviceAccountKey.json"):
            if not firebase_admin._apps:
                cred = credentials.Certificate("serviceAccountKey.json")
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            # lightweight ping: list collections (first one)
            cols = [c.id for c in db.collections()]
            results.append(CheckResult("Firebase (SA key)", True, time.time() - s,
                                       f"collections={cols[:5]}..."))
        else:
            if not firebase_admin._apps:
                firebase_admin.initialize_app()
            db = firestore.client()
            cols = [c.id for c in db.collections()]
            results.append(CheckResult("Firebase (default)", True, time.time() - s,
                                       f"collections={cols[:5]}..."))
    except Exception as exc:
        results.append(CheckResult("Firebase/Firestore", False, time.time() - s, str(exc)))
    return results

# ---------------------------------------------------------------------------
#  Baseline internet / HTTP connectivity
# ---------------------------------------------------------------------------
def _check_connectivity() -> List[CheckResult]:
    targets = [
        ("Google HEAD", "https://www.google.com", "head"),
        ("GitHub HEAD", "https://github.com", "head"),
    ]
    results: List[CheckResult] = []
    for name, url, method in targets:
        s = time.time()
        try:
            fn = requests.head if method == "head" else requests.get
            rv = fn(url, timeout=10, allow_redirects=True)
            ok = rv.status_code < 400
            results.append(CheckResult(name, ok, time.time() - s,
                                       f"HTTP {rv.status_code}" if not ok else ""))
        except Exception as exc:
            results.append(CheckResult(name, False, time.time() - s, str(exc)))
    return results

# ---------------------------------------------------------------------------
#  Reporter
# ---------------------------------------------------------------------------
def _print_results(category: str, items: List[CheckResult]) -> None:
    print(f"\n{_C.CYAN}{'-'*60}{_C.RESET}")
    print(f"{_C.BOLD}{category}{_C.RESET}")
    print(f"{_C.CYAN}{'-'*60}{_C.RESET}")
    for r in items:
        if r.skipped:
            print(f"  {_skip(r.name, r.msg)}")
        elif r.ok:
            print(f"  {_ok(r.name, r.elapsed)}")
        else:
            print(f"  {_fail(r.name, r.elapsed, r.msg)}")

def _write_json_report(all_results: Dict[str, List[CheckResult]], path: str = "api_check_report.json") -> None:
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {},
        "details": {}
    }
    total_pass = total_fail = total_skip = 0
    for cat, items in all_results.items():
        cat_pass = sum(1 for r in items if r.ok and not r.skipped)
        cat_fail = sum(1 for r in items if not r.ok and not r.skipped)
        cat_skip = sum(1 for r in items if r.skipped)
        out["summary"][cat] = {"pass": cat_pass, "fail": cat_fail, "skip": cat_skip}
        total_pass += cat_pass
        total_fail += cat_fail
        total_skip += cat_skip
        out["details"][cat] = [
            {"name": r.name, "status": "pass" if r.ok else ("skip" if r.skipped else "fail"),
             "elapsed": round(r.elapsed, 3), "message": r.msg}
            for r in items
        ]
    out["summary"]["total"] = {"pass": total_pass, "fail": total_fail, "skip": total_skip}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n{_C.CYAN}{'-'*60}{_C.RESET}")
    print(_info(f"JSON report written -> {path}"))

# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"\n{_C.BOLD}Course Verifier - API Checker{_C.RESET}")
    print(f"Started at {datetime.now().isoformat()}\n")

    all_results: Dict[str, List[CheckResult]] = {}

    # 1. Internal
    all_results["Internal Flask Routes"] = _check_internal()

    # 2. LLM Providers
    all_results["LLM / AI Providers"] = _check_llm()

    # 3. Firebase
    all_results["Firebase / Firestore"] = _check_firebase()

    # 4. Connectivity
    all_results["External Connectivity"] = _check_connectivity()

    # ---- Print ----
    for cat, items in all_results.items():
        _print_results(cat, items)

    # ---- Totals ----
    total_pass = total_fail = total_skip = 0
    for items in all_results.values():
        total_pass += sum(1 for r in items if r.ok and not r.skipped)
        total_fail += sum(1 for r in items if not r.ok and not r.skipped)
        total_skip += sum(1 for r in items if r.skipped)

    print(f"\n{_C.CYAN}{'='*60}{_C.RESET}")
    print(f"  {_C.BOLD}TOTAL:{_C.RESET}  {_C.GREEN}{total_pass} passed{_C.RESET}   "
          f"{_C.RED}{total_fail} failed{_C.RESET}   {_C.YELLOW}{total_skip} skipped{_C.RESET}")
    print(f"{_C.CYAN}{'='*60}{_C.RESET}\n")

    _write_json_report(all_results)

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
