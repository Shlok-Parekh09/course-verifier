# Autonomous Course Verifier 3.5 — Issue Classification Edition

The **Autonomous Course Verifier** is a robust, local-first Python application designed to automatically extract course information from structurally complex PDFs, cross-reference university rankings, and autonomously navigate the web to verify course details (cost, duration, mode, skills, university, country, language) against official university websites.

This version introduces **automatic issue classification** — every verification result is now tagged as either a **Website Issue** (broken link, server error, WAF block, timeout, etc.) or a **Course Issue** (data mismatch like wrong cost, duration, discontinued course, etc.). It also adds **speed optimizations** like preflight dead-link detection and domain-health caching to skip repeatedly failing sites instantly.

---

## 🚀 Key Features

### 1. Intelligent PDF Parsing
- **Geometric Slicing:** Parses PDFs by slicing pages into quadrants to isolate individual course boxes.
- **Fuzzy University Matching:** Detects university names using a fuzzy-matching mechanism against a global database of over 10,000 institutions.
- **Visual Badge Detection:** Uses OpenCV mask analysis and Tesseract OCR to identify "QS", "NIRF", and "Free/Scholarship" badges.

### 2. Rank Verification Pipeline
- **Offline Data:** Leverages local ranking data (`rankings.db`) to verify university standings without external API calls.
- **Semantic Normalization:** Employs `difflib` for semantic name matching to ensure accuracy across different naming conventions.

### 3. Autonomous Web Verification & Smart Browsing
- Uses `undetected_chromedriver` (uc) to bypass standard bot protections (Cloudflare).
- **Persistent Chrome Profiles:** Automatically saves your cookies and sessions inside the `chrome_profile` directory, ensuring you stay logged in to platforms like Coursera and NDU without triggering captchas.
- **NDU Batch Caching:** For NDU (National Institute of Electronics and Information Technology) courses, it efficiently navigates to "Browse by Category", scrapes all pages of course cards into memory, and verifies multiple courses rapidly without redundant page loads.
- Executes precise Google Search queries using `site:` operators if internal site search fails.

### 4. Local LLM Verification Engine
- Analyzes scraped web text against PDF details using **local semantic verification**.
- Attempts to query a fast API (OpenRouter, Gemini, NVIDIA, Groq, Mistral, SambaNova), and automatically fails over to the next provider if one fails.
- If no LLM is available, falls back to a custom `spaCy` NLP Regex Engine to perform sentence-level context parsing.

### 5. Report Generation
- Generates a beautifully formatted output PDF (`_AUTONOMOUS_VERIFIED.pdf`) detailing each course, highlighting discrepancies in red and matches in green.
- Preserves visual proof by saving screenshots of the original PDF quadrants and the scraped websites into the `verification_screenshots/` folder.

---

## 🆕 What's New in v3.5

### 🔴 Automatic Issue Classification
Every verification outcome is now automatically classified into one of two buckets with specific sub-types:

#### **Website Issue** — The site itself is broken / inaccessible
- `404_not_found` — Page does not exist
- `ssl_error` — SSL / Privacy error
- `server_error` — HTTP 500 / 503 / 502
- `blocked_by_waf` — Cloudflare, Captcha, WAF
- `timeout` — Connection / page-load timeout
- `dns_fail` — Domain unreachable / DNS failure
- `login_required` — Paywall / login gate
- `site_down` — Maintenance / temporarily unavailable
- `browser_crash` — Selenium driver crashed
- `redirect_loop` — Infinite redirect loop

#### **📋 Course Issue** — The page loads, but data doesn't match
- `name_mismatch`
- `cost_mismatch`
- `duration_mismatch`
- `university_mismatch`
- `country_mismatch`
- `mode_mismatch`
- `language_mismatch`
- `skills_mismatch`
- `course_discontinued`
- `course_replaced`
- `wrong_url`
- `multiple_mismatches`

These are stored in every course record as:
```json
{
  "issue_category": "website_issue",
  "issue_sub_type": "404_not_found",
  "retry_count": 0,
  "error_screenshot_path": "verification_screenshots/.../course_5_404_not_found.png"
}
```

---

### ⚡ Speed Optimizations

#### **Preflight URL Check**
Before opening the heavy browser, the verifier fires a lightweight `HEAD` request. If the server returns **404, 500, 502, 503, 403, timeout, or DNS error**, the course is fast-failed immediately — saving **10–20 seconds per dead link**.

#### **Domain Health Cache**
A shared TTL cache tracks how many website issues each domain has experienced. If a domain racks up **5+ failures** within 10 minutes, all subsequent courses from that domain are **instantly skipped** with a fast-fail message. No more wasting 6 Chrome instances on a completely down university site.

#### **Domain-Wide Health Warnings**
If a domain accumulates **3+ website issues**, the dashboard warns: "Possible site-wide outage for `<domain>`". You can then decide whether to retry later or contact the university's IT team.

---

### 📊 Dashboard Enhancements (`dashboard.py` + `templates/index.html`)

#### New KPI Cards
| Card | Description |
|---|---|
| **Website Issues** | Count + percentage of courses that failed because the site is broken |
| **Course Issues** | Count + percentage of courses where the data didn't match |

#### New Chart: Issue Category Breakdown
A doughnut chart shows the split between:
- 🔴 **Website Issues**
- 🟠 **Course Issues**
- 🟢 **Verified**

#### Color-Coded Tables
Both the **Recent Verifications** table and the **All Courses** table now display the actual `issue_sub_type` as the badge text:
- 🔴 Red badge = `website_issue` (e.g., "404 not found", "SSL error")
- 🟠 Orange badge = `course_issue` (e.g., "Cost Mismatch", "Multiple Mismatches")
- 🟢 Green badge = `verified`

Hovering over the badge shows the full `issue_category`.

#### New API Endpoints / JSON Fields
`/api/data.json` now includes:
```json
{
  "stats": {
    "website_issues": 12,
    "course_issues": 8
  },
  "website_sub_counts": { "404_not_found": 7, "timeout": 5 },
  "course_sub_counts": { "cost_mismatch": 4, "multiple_mismatches": 4 },
  "domain_warnings": [
    { "domain": "Some University", "issue_count": 5 }
  ],
  "website_issue_list": [...],
  "course_issue_list": [...]
}
```

---

### 📁 Excel Export Enhancements
`AUTONOMOUS_VERIFIED.xlsx` now includes **4 new columns**:

| Column | Description |
|---|---|
| `Issue Category` | `website_issue` / `course_issue` / `verified` |
| `Issue Sub-Type` | Specific sub-type (e.g., `404_not_found`, `cost_mismatch`) |
| `Retry Count` | How many times the verifier attempted this course |
| `Error Screenshot` | File path to the captured screenshot on error |

---

## ⚙️ Setup

### 1. Environment Variables
Copy `.env.example` to `.env` and add your API keys:
```bash
OPENROUTER_KEY_1=...
GEMINI_KEY_1=...
NVIDIA_KEY_1=...
GROQ_API_KEY_1=...
MISTRAL_API_KEY_1=...
SAMBANOVA_API_KEY_1=...
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Prepare Data
Ensure `rankings.db` is in the root directory.

---

## 💻 Usage

### Run the Verifier
```bash
python autonomous_course_verifier.py
```
- **Input:** Provide the path to your target course PDF.
- **Process:** The script extracts data, verifies rankings, browses the web, classifies issues, and saves evidence.
- **Output:**
  - `verification_screenshots/<timestamp>/` — Screenshots of PDF quadrants and web pages
  - `verification_screenshots/<timestamp>/website_errors/` — Screenshots captured specifically when a **Website Issue** is detected
  - `AUTONOMOUS_VERIFIED.xlsx` — Full spreadsheet with issue classification
  - `_AUTONOMOUS_VERIFIED.pdf` — Human-readable PDF report

### Run the Dashboard
```bash
python dashboard.py
```
Then open `http://localhost:5000` in your browser.

---

## 📂 Project Structure

| File / Folder | Purpose |
|---|---|
| `autonomous_course_verifier.py` | Core engine (Parser, Scraper, Issue Classifier, Logic) |
| `llm_manager.py` | Multi-provider LLM routing with key rotation and rate-limiting |
| `db_manager.py` | SQLite manager for QS / NIRF ranking lookups |
| `dashboard.py` | Flask web dashboard with analytics and live filtering |
| `templates/index.html` | Premium dark-themed dashboard UI |
| `static/app.js` | Frontend charts, tables, modal logic |
| `static/style.css` | Dashboard styling |
| `CombinedWork.xlsx` | Supplemental verification data with hyperlinks |
| `rankings.db` | Offline university ranking database |
| `public/api/` | Static JSON exports (`courses.json`, `data.json`) for Firebase hosting |
| `verification_screenshots/` | Captured screenshots organized by run timestamp |

---

## 🧠 How Issue Classification Works

1. **Website Issue detection** happens first:
   - Preflight `HEAD` request catches HTTP errors instantly
   - If the browser loads, the title and body text are checked for: 404, "service unavailable", "privacy error", "verify you are human", "under maintenance", etc.
   - A screenshot is saved to `website_errors/` and the domain health cache is updated

2. **Course Issue detection** happens when the page loads successfully but verification fails:
   - The verifier checks 7 attributes: Name, Cost, Duration, Mode, Language, Skills, University
   - If 3+ attributes fail, it's labeled `multiple_mismatches`
   - Otherwise the first failed attribute determines the `issue_sub_type`
   - The result is stored alongside `web_status` and `reason`

3. **Dashboard consumption**:
   - `dashboard.py` reads `issue_category` when loading courses and maps it to `status`
   - The frontend renders the appropriate badge color and label

---

## 🔒 Domain Health Cache (TTL)

```python
# Shared across all verifier threads
_DOMAIN_HEALTH = DomainHealthCache(ttl_seconds=600)

# Mark a failure:
_DOMAIN_HEALTH.mark_issue("iitm.ac.in", "website_issue", "timeout")

# Query:
_DOMAIN_HEALTH.is_healthy("iitm.ac.in")   # False if 3+ issues
_DOMAIN_HEALTH.should_skip("iitm.ac.in")  # True if 5+ issues → fast-skip
```

This means if IIT Madras's site goes down during a batch run, the verifier stops wasting Chrome instances on it after the 5th failure and moves on instantly.

---

## 🛠 Troubleshooting

| Problem | Solution |
|---|---|
| Too many timeouts | Domain health cache will auto-skip repeat offenders. Lower `ttl_seconds` in `DomainHealthCache` if you want quicker recovery. |
| Preflight marks good links as bad | Some servers reject `HEAD`. The preflight automatically falls back to a minimal `GET` with stream, but if a server still blocks it, you can disable preflight by commenting out the `_preflight_url_check` call. |
| Screenshot folder too large | The `website_errors/` subfolder only grows for broken links. You can safely archive or delete old `verification_screenshots/` directories. |
| Dashboard not showing issue badges | Ensure `dashboard.py` has the `ISSUE_*` constants at the top and `load_courses()` maps `issue_category` to `status`. |

---

*Developed for autonomous educational data verification.*
