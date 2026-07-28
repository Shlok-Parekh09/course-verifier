"""
fix_specific_indices.py
========================
Fixes domain classification for ONLY two specific index ranges:
  - IDs 337-444  (Foundational band): set domain to "Master's Degree"
                                       (skip Free / Free to Audit entries)
  - IDs 1558-1585 (Network Infra band): set domain to "Post Graduate Certificate"
                                         (skip Free / Free to Audit entries)

Updates both:
  1. frontend/1.json  (local source file)
  2. Cloudflare KV via the Worker /api/update_domain  (live website)
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

INPUT_JSON = "frontend/1.json"
CF_WORKER_URL = os.environ.get("CF_WORKER_URL", "https://course-verifier-api.shlokparekh08.workers.dev")
CF_KV_PUSH_KEY = os.environ.get("CF_KV_PUSH_KEY", "courseverify_secure_push_key_2026")

# ── Targeted ranges ──────────────────────────────────────────────────
RANGES = [
    {"start": 337, "end": 444,  "domain": "Master's Degree"},
    {"start": 1558, "end": 1585, "domain": "Post Graduate Certificate"},
]

# Domains that should NEVER be overridden — they are pricing/access bands
# that take precedence over academic-level classification.
PROTECTED_DOMAINS = {
    "Free",
    "Free to Audit",
    "High Value Low Cost",
}


def main():
    print(f"[*] Loading {INPUT_JSON}...")
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"    {len(data)} courses loaded.")

    fixed_local = 0
    cf_updates = []

    for c in data:
        cid = c.get("id")
        if cid is None:
            continue

        new_domain = None
        for r in RANGES:
            if r["start"] <= cid <= r["end"]:
                new_domain = r["domain"]
                break

        if new_domain is None:
            continue  # Not in any targeted range

        current_domain = c.get("domain", "")

        # Never overwrite Free / Free to Audit / High Value Low Cost
        if current_domain in PROTECTED_DOMAINS:
            print(f"  SKIP id={cid:>5}: protected domain {current_domain!r} | {c.get('name','')[:50]}")
            continue

        if current_domain != new_domain:
            print(f"  FIX  id={cid:>5}: {current_domain!r:>25} -> {new_domain!r} | {c.get('name','')[:50]}")
            c["domain"] = new_domain
            fixed_local += 1

        # Include in CF update payload regardless (idempotent)
        cf_updates.append({"id": cid, "domain": new_domain})

    print(f"\n[*] {fixed_local} entries updated locally.")
    print(f"[*] {len(cf_updates)} entries to push to Cloudflare.")

    # ── Save local JSON ──────────────────────────────────────────────
    with open(INPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] {INPUT_JSON} saved.")

    # ── Push to Cloudflare ───────────────────────────────────────────
    print(f"\n[*] Pushing domain updates to Cloudflare...")
    headers = {
        "Authorization": f"Bearer {CF_KV_PUSH_KEY}",
        "Content-Type": "application/json",
    }
    chunk_size = 50
    for i in range(0, len(cf_updates), chunk_size):
        chunk = cf_updates[i : i + chunk_size]
        payload = {"domain_updates": chunk}
        try:
            resp = requests.post(
                f"{CF_WORKER_URL}/api/update_domain",
                json=payload,
                headers=headers,
                timeout=30,
            )
            print(f"  Batch {i // chunk_size + 1}: {resp.status_code} - {resp.text[:120]}")
        except Exception as e:
            print(f"  Batch {i // chunk_size + 1}: ERROR - {e}")

    print("\n[OK] Done.")


if __name__ == "__main__":
    main()
