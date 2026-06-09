# Autonomous Course Verifier 3.0

The **Autonomous Course Verifier** is a robust, local-first Python application designed to automatically extract course information from structurally complex PDFs, cross-reference university rankings, and autonomously navigate the web to verify course details (such as cost, duration, mode, and skills) against the university's official website.

## Core Features

1. **Intelligent PDF Parsing**
   - Parses the given PDF (e.g. `HIGH VALUE LOW COST (1).pdf`) by geometrically slicing pages into quadrants.
   - Extracts course details, detecting the university name using a fuzzy-matching mechanism against a database of over 10,000 global universities.
   - Visually detects "QS", "NIRF", and "Free/Scholarship" badges using OpenCV mask analysis and fallback OCR (Tesseract).

2. **Rank Verification Pipeline**
   - Loads offline ranking data (`nirf_ranked.csv`, `qs_ranked.csv`) without API calls.
   - Normalizes names and applies difflib-based semantic matching to verify if a university is truly ranked.

3. **Autonomous Web Verification & Smart Browsing**
   - Uses `undetected_chromedriver` (uc) to bypass standard bot protections (Cloudflare).
   - **Persistent Chrome Profiles:** Automatically saves your cookies and sessions inside the `chrome_profile` directory, ensuring you stay logged in to platforms like Coursera and NDU without triggering captchas.
   - **NDU Batch Caching:** For NDU (National Institute of Electronics and Information Technology) courses, it efficiently navigates to "Browse by Category", scrapes all pages of course cards into memory, and verifies multiple courses rapidly without redundant page loads.
   - Executes precise Google Search queries using `site:` operators if internal site search fails.

4. **Parallel Fee Intelligence Layer [NEW]**
   - A completely independent, parallel `fee_engine` package dedicated to intelligent fee extraction.
   - **Intelligent DOM Navigation:** Uses `Playwright` to navigate nested accordions, stabilize dropdowns, and automatically dismiss overlays/cookie banners.
   - **Multi-Format Parsing:** Extracts text from web pages, PDFs (`PyMuPDF`), Images (`pytesseract`), and DOCX files.
   - **Regex & Context Validation:** Uses structured regex targeting alongside `llm_manager.py` to extract standardized fee amounts and assign Confidence Scores (`HIGH`, `MEDIUM`, `LOW`).

5. **Local LLM Verification Engine**
   - Analyzes scraped web text against PDF details using **local semantic verification**.
   - Attempts to query a fast API (OpenRouter, Gemini), and automatically falls back to **Local Ollama** (e.g., `llama3.2`) if the network is down or APIs fail.
   - If no LLM is available, falls back to a custom `spaCy` NLP Regex Engine to perform sentence-level context parsing.

6. **Report Generation**
   - Generates a beautifully formatted output PDF (`_AUTONOMOUS_VERIFIED.pdf`) detailing each course, highlighting discrepancies in red and matches in green.
   - The parallel `fee_engine` generates dedicated Excel sheets (`fee_verification.xlsx`) and JSON audit logs.
   - Preserves visual proof by saving screenshots of the original PDF quadrants and the scraped websites into the `verification_screenshots/` and `fee_reports/screenshots/` folders.

## Setup

1. **Environment Variables**
   - Copy `.env.example` to `.env`.
   - Fill in your Coursera/NDU credentials and LLM API keys.

2. **Dependencies**
   - Install required packages:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

## File Structure

- `autonomous_course_verifier.py`: The main engine containing the PDF parser, ranking logic, and web scraper.
- `fee_engine/`: The independent parallel fee extraction pipeline (`fee_crawler.py`, `fee_parser.py`, `fee_verifier.py`, `fee_reporter.py`, `main.py`).
- `run_full_system.py`: Multi-threaded wrapper to launch both the legacy verifier and the Fee Intelligence Layer simultaneously.
- `generate_report_only.py`: The PDF drawing logic (using `reportlab`) that produces the final visually-stunning output.
- `llm_manager.py`: Handler for intelligent LLM routing (OpenRouter, Gemini, Ollama).
- `CombinedWork.xlsx` & `fees.xlsx`: Supplemental course data used for verification.
- `qs_ranked.csv` & `nirf_ranked.csv`: Offline ranking data.
- `chrome_profile/`: Your persistent browser session storage.

## Usage

**Run both pipelines in parallel:**
```bash
python run_full_system.py
```

**Run only the Main Verifier script on a target PDF:**
```bash
python autonomous_course_verifier.py
```

**Run only the Fee Intelligence Layer:**
```bash
python fee_engine/main.py
```
