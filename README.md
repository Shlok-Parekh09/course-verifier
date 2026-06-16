# Autonomous Course Verifier 3.0

The **Autonomous Course Verifier** is a robust, local-first Python application designed to automatically extract course information from structurally complex PDFs, cross-reference university rankings, and autonomously navigate the web to verify course details (such as cost, duration, mode, and skills) against official university websites.

## 🚀 Key Features

### 1. Intelligent PDF Parsing
- **Geometric Slicing:** Parses PDFs by slicing pages into quadrants to isolate individual course boxes.
- **Fuzzy University Matching:** Detects university names using a fuzzy-matching mechanism against a global database of over 10,000 institutions.
- **Visual Badge Detection:** Uses OpenCV mask analysis and Tesseract OCR to identify "QS", "NIRF", and "Free/Scholarship" badges.

### 2. Rank Verification Pipeline
- **Offline Data:** Leverages local ranking data (`rankings.db`) to verify university standings without external API calls.
- **Semantic Normalization:** Employs `difflib` for semantic name matching to ensure accuracy across different naming conventions.

3. **Autonomous Web Verification & Smart Browsing**
   - Uses `undetected_chromedriver` (uc) to bypass standard bot protections (Cloudflare).
   - **Persistent Chrome Profiles:** Automatically saves your cookies and sessions inside the `chrome_profile` directory, ensuring you stay logged in to platforms like Coursera and NDU without triggering captchas.
   - **NDU Batch Caching:** For NDU (National Institute of Electronics and Information Technology) courses, it efficiently navigates to "Browse by Category", scrapes all pages of course cards into memory, and verifies multiple courses rapidly without redundant page loads.
   - Executes precise Google Search queries using `site:` operators if internal site search fails.

4. **Local LLM Verification Engine**
   - Analyzes scraped web text against PDF details using **local semantic verification**.
   - Attempts to query a fast API (OpenRouter, Gemini), and automatically falls back to **Local Ollama** (e.g., `llama3.2`) if the network is down or APIs fail.
   - If no LLM is available, falls back to a custom `spaCy` NLP Regex Engine to perform sentence-level context parsing.

5. **Report Generation**
   - Generates a beautifully formatted output PDF (`_AUTONOMOUS_VERIFIED.pdf`) detailing each course, highlighting discrepancies in red and matches in green.
   - Preserves visual proof by saving screenshots of the original PDF quadrants and the scraped websites into the `verification_screenshots/` folder.

## Setup

1. **Environment Variables**
   - Copy `.env.example` to `.env`.
   - Add your API keys (OpenRouter/Gemini) and platform credentials (Coursera/NDU).

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Prepare Data:**
   Ensure `rankings.db` is in the root directory.

## 💻 Usage

Run the main verifier script on a target PDF:
```bash
python autonomous_course_verifier.py
```
- **Input:** Provide the path to your target course PDF.
- **Process:** The script will extract data, verify rankings, browse the web, and run LLM analysis.
- **Output:** Check the `verification_screenshots/` folder for proof and the final generated PDF report.

## 📂 Project Structure

- `autonomous_course_verifier.py`: Core engine (Parser, Scraper, Logic).
- `generate_report_only.py`: PDF report generation logic.
- `llm_manager.py`: LLM routing and fallback management.
- `dashboard.py`: (Optional) Web dashboard for viewing results.
- `CombinedWork.xlsx`: Supplemental verification data.
- `rankings.db`: Offline university ranking database.

---
*Developed for autonomous educational data verification.*
