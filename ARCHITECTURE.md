# Course Verifier — Architecture & Recent Changes

This document explains **how the course verifier works end-to-end** and **exactly what was changed** in the recent speed + stability work (commits `3bcf458`, `2d84a47`, `c149e1e`). It's written so you can understand the whole picture without reading the 8,000-line source file.

> Companion to `README.md` (which describes the original feature set). This file focuses on the *current* architecture and the *recent* changes.

---

## 1. What the project does (in one paragraph)

Take a **PDF course catalog** (`link_compile_trimmed.pdf`) → for each course, **verify its details** (cost, duration, mode, language, country, university, skills) against the course's **live website** using a **cloud LLM** → produce a **PDF report** marking each field MATCH (green) or FALSE (red). It runs in **GitHub Actions** so a 100-page catalog can be processed unattended.

---

## 2. The pipeline (4 steps)

The launcher `run_verifier_pages.py` drives these in order:

| Step | Function | What it does | Browser? |
|------|----------|--------------|----------|
| **Step 1** | `extract_and_parse()` | Parse the PDF: slice each page into quadrants, extract course name/URL/cost/duration/etc. | No |
| **Step 1.5** | `extract_visuals_for_range()` | Render each course's PDF quadrant to an image, detect QS/NIRF/Free/Scholarship **badges** via OpenCV + Tesseract OCR. *(Sequential loop.)* | No |
| **Step 3** | `autonomous_web_verify()` | For each course: fetch its website, extract text, ask the LLM to verify the details. **6 browsers in parallel.** This is the big one. | Yes (uc) |
| **Step 2** | `verify_rankings()` | Confirm QS/NIRF ranking status for each university via the offline `rankings.db`. | No |
| **Step 4** | `generate_pdf_report()` | Build the colored PDF report (`Verification_Report_Pages_*.pdf`). | No |

(Note the numbering oddity: Step 3 runs before Step 2. That's intentional — web verification is the expensive part.)

**Output artifacts** (uploaded by the workflow): the PDF report, the checkpoint JSON, and screenshots.

---

## 3. Key files

| File | Role |
|------|------|
| `autonomous_course_verifier.py` (~8,200 lines) | The whole engine: PDF parse, badge OCR, web verification, rankings, report. |
| `run_verifier_pages.py` | CLI launcher. Parses `--pages START END --page-offset N --fresh --no-email`, calls the steps above. |
| `llm_manager.py` | LLM router. Talks to **ollama.com cloud** (the only provider configured). |
| `db_manager.py` | Thread-safe SQLite pool over `rankings.db` (QS/NIRF membership lookups). |
| `email_sender.py` | SMTP sender for completion notifications. |
| `.github/workflows/verify-courses.yml` | The GitHub Actions workflow (see §7). |
| `.env` | Local secrets (**not committed** — OLLAMA_API_KEY, SMTP creds). |

---

## 4. The web-verification step in detail (Step 3)

This is where ~90% of the runtime goes, and where all the recent changes live. For each course, `process_course()` used to do this:

1. **Claim a browser** from a pool of 6 `undetected_chromedriver` (uc) Chrome instances.
2. **Preflight** the URL with a HEAD/GET request (`_preflight_url_check`) — fast-fail dead links before spending a browser.
3. **Navigate** (`_safe_get`) with WAF/captcha/SSL bypass logic.
4. **Extract page text** (`_extract_page_text`): inject JS to expand accordions, click fee tabs, read `<body>` text, deep-extract hidden elements/Shadow DOM, OCR any embedded fee images.
5. **Expand more** accordions/tabs (`js_accordions`, `js_all_tabs`, `js_intl`), scroll, re-extract.
6. **Deep-crawl**: find fee/syllabus sub-pages and PDFs, fetch them, append their text.
7. **Send the text to the LLM** (`_verify_details_with_llm`) → get a JSON verdict (cost/duration/mode/language/country/university/skills match flags).
8. **Assemble the verdict**: apply heuristics (Swayam/NPTEL fee override, platform-online mode, IIT/IIIT abbreviation matching, defaults), set `web_status = MATCH`/`FALSE`, write all fields + the checkpoint.

**The bottleneck:** every course paid a full Chrome navigation + crash-prone JS injection + ~5s Chrome rebuild after every crash, and the LLM was sent **up to 1,000,000 characters** of page text.

---

## 5. The problems we hit (and why)

1. **Local Ollama fallback kept failing** (Connection refused on localhost:11434) → removed; cloud Ollama only now.
2. **Doubled/malformed API URLs** (`/api/api/generate`) → normalized with `urlsplit` so any secret shape resolves to `https://ollama.com/api/generate`.
3. **Slow LLM model** (`nemotron-3-super:cloud`, ~32s/call, timed out on big prompts) → switched to **`nemotron-3-nano:30b`** (~11–14s, valid JSON, 9× faster).
4. **chromedriver binary race** ("Text file busy" / "No such file") when several threads recovered browsers at once → serialized the recovery `uc.Chrome()` call with `browser_init_lock`.
5. **OOM (exit 143) on long runs** — the old `taskkill` was Windows-only and silently no-op'd on the Linux CI runner, so orphan Chrome/chromedriver processes accumulated → made process-killing **cross-platform** (`os.kill` SIGKILL on Linux) and also kill the chromedriver service process. *(commit `3bcf458`)*
6. **`os` UnboundLocalError** — the cross-platform kill added `import subprocess, os, signal` *directly inside `process_course`*, which (by Python's compile-time scoping) made `os` a function-local for the whole function, breaking earlier `os` references (the recovery loop's `os.path.join` and the per-course checkpoint save's `os.path.basename`). This silently broke checkpoint saves on **21 of 22 courses** and broke browser recovery. *(fixed in `c149e1e`)*
7. **Speed** — even when stable, ~35s/course × hundreds of courses is slow, and 6 separate Chrome processes eat RAM.

---

## 6. What I changed (the recent commits)

### `3bcf458` — stability (chromedriver race + orphan OOM)
- Wrapped the inline-recovery `uc.Chrome()` in `browser_init_lock` so threads don't race the chromedriver binary patcher.
- Made `kill_drv` and the proactive-restart kill **cross-platform**: `taskkill /F` on Windows, `os.kill(SIGKILL)` on Linux (CI), plus killing the chromedriver **service** process, not just the browser. Stops orphan accumulation → no more exit-143 OOM on long runs.

### `2d84a47` — **Phase 1 + Phase 2 (the speed work)**

#### Phase 1: LLM text truncation (1,000,000 → 25,000 chars)
- New helper `_keyword_aware_truncate(text, budget, course)`: instead of a naive head-truncate, it keeps the **first 2 paragraphs** (university/title context) plus the **highest-scoring paragraphs** by cost/fee/duration/skill keyword hits and course/university name tokens, preserving original order.
- `_verify_details_with_llm` now caps the page text at **`VERIFIER_LLM_TEXT_BUDGET`** (default 25,000) instead of 1,000,000. The `--- EXCEL FEES DATA ---` / `--- EXCEL SYLLABUS DATA ---` blocks are kept in full (small, high-signal).
- **Effect:** ~40× less input to the LLM → faster LLM calls, with the keyword-aware selection making sure the important fee/duration paragraphs survive the cut.

#### Phase 2: HTTP-first extraction (skip the browser for static pages)
- New method `_try_http_first(course)`: fetch the course page with a plain `requests.get` + BeautifulSoup. If the text is **rich enough** and the page **isn't a WAF/challenge page**, verify directly with the LLM and **skip the browser entirely**.
  - **WAF/challenge detection:** skip if the text contains `just a moment`, `enable javascript`, `cloudflare`, `access denied`, `verify you are human`, etc., or is very short.
  - **Sufficiency gate:** only short-circuit when `len(text) >= 1500` AND ≥2 of {cost/fee signals, duration signals, skill signals} are present.
  - **Safety design (important):** it only short-circuits **clear MATCH cases**, mirroring the browser path's exact `is_match` rule (`name/title/url score ≥ 0.80`, or `uni_match and sk_match`). Anything uncertain **returns None → the browser path runs unchanged**, so FALSE/ambiguous cases have **exact parity** with the old behavior. No accuracy risk on the hard cases.
  - Reuses existing primitives: `_fetch_url_robust` (PDF/Excel), `_search_excel_for_links` (fees/syllabus).
- Inserted into `process_course` right after the preflight check, **before** browser navigation. If it succeeds, it writes the verdict + checkpoint cache and exits early — the browser is never driven for that course.
- Enabled only when **`VERIFIER_HTTP_FIRST`** is set (default off in code, on via the workflow input).

#### Measured result (172–177, 22 courses):
- **19 of 22 courses (86%) verified via plain HTTP — no browser at all.**
- Verification span: ~67 seconds for those 19 courses (~3.5 s/course including the LLM).
- All 19 = MATCH with strong scores (Name 1.00, Uni 1.00, etc.).
- Total wall-clock **4.37 min** (incl. ~3 min CI setup).
- The 3 browser-path courses included 1 uc crash (Universidad ICESI, a JS-heavy site) — recovered correctly after the `os` fix, retried, then skipped after 2 crashes (the exact instability Phase 3 will remove).

### `c149e1e` — fix the `os` UnboundLocalError
- Dropped `os` from the local `import subprocess, os, signal` in `process_course`'s finally block (use the module-level `os`). This un-broke browser recovery **and** per-course checkpoint saves.
- Before fix: 24 `os` errors, 21 failed checkpoint saves, 3 failed recoveries. After fix: **0, 0, 0** (and 1 successful browser recovery).

---

## 7. The GitHub Actions workflow

`.github/workflows/verify-courses.yml` is a `workflow_dispatch` with inputs:

| Input | Default | Meaning |
|-------|---------|---------|
| `start_page` | 172 | First original PDF page |
| `end_page` | 172 | Last original PDF page |
| `page_offset` | 171 | `original_page = cropped_page + offset` (PDF starts at original p.172, so offset 171) |
| `browsers` | 2 | Parallel browser count (the workflow `sed`-rewrites `NUM_BROWSERS = 6`) |
| `http_first` | 1 | **1** = enable HTTP-first extraction; 0 = browser-only (old behavior) |
| `llm_text_budget` | 25000 | Max chars of page text sent to the LLM |

Env vars passed to the verifier: `VERIFIER_HTTP_FIRST`, `VERIFIER_LLM_TEXT_BUDGET`, plus the Ollama secrets (`OLLAMA_API_URL`, `OLLAMA_MODEL`, `OLLAMA_API_KEY`).

Additional tunable env vars (not in the workflow UI, settable as repo env/secret if needed):
- `VERIFIER_HTTP_MIN_CHARS` (default 1500) — min HTTP text length to short-circuit.
- `VERIFIER_HTTP_MIN_SIGNALS` (default 2) — min field-signal groups required to short-circuit.

**Trigger a run locally:**
```bash
gh workflow run verify-courses.yml \
  -f start_page=172 -f end_page=272 -f page_offset=171 \
  -f browsers=6 -f http_first=1 -f llm_text_budget=25000 \
  --ref yug-render-deploy
```

**Swap the LLM model** (no code change needed):
```bash
printf 'nemotron-3-nano:30b' | gh secret set OLLAMA_MODEL --repo Shlok-Parekh09/course-verifier
```

---

## 8. How to read a run's results

In the Actions logs, look for:
- `[HTTP-FIRST] Verified via plain HTTP (no browser). status=MATCH | ...` → course verified without a browser (the fast path).
- `Started verifying: <name>` → a course began (on a browser thread).
- `Browser successfully recovered.` → a crashed uc browser was rebuilt (now works after `c149e1e`).
- `crashed 2 times. Skipping.` → a course that kept crashing uc (Phase 3 will fix these).
- `Step 2/4: Verifying QS/NIRF rankings` → rankings step; `QS/NIRF match confirmed for X: Ranked` means the university is in the QS/NIRF lists.
- `cannot access local variable 'os'` / `Failed to save checkpoint` → **should be 0** after `c149e1e`. If you see these, the `os` fix regressed.

**Artifacts** (download from the run page):
- `report-pdf` → `Verification_Report_Pages_*.pdf` (the colored report).
- `verifier-checkpoint` → `autonomous_verified_link_compile_trimmed.pdf.json` (per-course results; used for `--resume`).
- `screenshots` → saved website/PDF screenshots.

---

## 9. What's next — Phase 3 (Playwright) and Phase 4

The remaining instability is the **uc browser layer itself**: `invalid session id` / `target closed` crashes on JS-heavy sites, and 6 separate Chrome processes. The plan (see `~/.claude/plans/synthetic-enchanting-crayon.md`):

- **Phase 3 — Playwright shim:** replace `undetected_chromedriver`/Selenium with Playwright (sync API) via a thin `BrowserPage` shim that mimics the Selenium `driver` interface, so the ~50 `execute_script` call sites barely change. Architecture: **1 shared `chromium.launch()` + N `new_context()`** (one per worker) → ~40–55% less RAM, no chromedriver-binary race, near-instant context recreation instead of 5s Chrome rebuilds. Behind `VERIFIER_BACKEND=playwright` (default `uc`) so it's reversible.
- **Phase 4 — cleanup:** remove uc/Selenium from `requirements.txt` and the workflow once Playwright passes a full 172–272 run.

Phase 3 directly removes the crash-retry churn that makes long runs (like 172–272) stretch beyond the HTTP-first fast path.

---

## 10. Quick mental model

```
PDF catalog
   │  (Step 1: parse into ~4 courses/page)
   ▼
Course list (name, url, cost, duration, ...)
   │  (Step 1.5: OCR badges — sequential)
   ▼
For each course ──► _preflight_url_check (HTTP HEAD/GET)
   │                    │ dead? → FALSE, done
   │                    ▼
   │              _try_http_first (HTTP-first)          ◄── NEW (Phase 2)
   │              fetch HTML + parse text
   │                    │ WAF or thin? → fall through to browser
   │                    │ rich + ≥2 signals + clear MATCH?
   │                    ▼ yes
   │              _verify_details_with_llm (text capped at 25K)  ◄── NEW (Phase 1)
   │                    ▼
   │              write verdict + checkpoint, done (NO browser)
   │
   └──── (fall-through) ──► uc Chrome: navigate + extract + accordions + deep-crawl
                                  ▼
                            _verify_details_with_llm (text capped at 25K)
                                  ▼
                            heuristics + verdict + checkpoint
   │
   ▼  (Step 2: QS/NIRF rankings via rankings.db)
   ▼  (Step 4: PDF report)
Final PDF + checkpoint JSON + screenshots
```