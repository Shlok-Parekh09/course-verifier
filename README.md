# Autonomous Course Verifier 3.0

The **Autonomous Course Verifier** is a robust, local-first Python application designed to automatically extract course information from structurally complex PDFs, cross-reference university rankings, and autonomously navigate the web to verify course details (such as cost, duration, mode, and skills) against official university websites.

## 🚀 Key Features

### 1. Intelligent PDF Parsing
- **Geometric Slicing:** Parses PDFs by slicing pages into quadrants to isolate individual course boxes.
- **Fuzzy University Matching:** Detects university names using a fuzzy-matching mechanism against a global database of over 10,000 institutions.
- **Visual Badge Detection:** Uses OpenCV mask analysis and Tesseract OCR to identify "QS", "NIRF", and "Free/Scholarship" badges.

### 2. Rank Verification Pipeline
- **Offline Data:** Leverages local ranking data (`nirf_ranked.csv`, `qs_ranked.csv`) to verify university standings without external API calls.
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

## File Structure

- `autonomous_course_verifier.py`: The main engine containing the PDF parser, ranking logic, and web scraper.
- `generate_report_only.py`: The PDF drawing logic (using `reportlab`) that produces the final visually-stunning output.
- `llm_manager.py`: Handler for intelligent LLM routing (OpenRouter, Gemini, Ollama).
- `CombinedWork.xlsx`: Supplemental course data used for verification.
- `qs_ranked.csv` & `nirf_ranked.csv`: Offline ranking data.
- `chrome_profile/`: Your persistent browser session storage.

## 💻 Usage

Run the main verifier script on a target PDF:
```bash
python autonomous_course_verifier.py
```
The script will ask for the path to your PDF. Once provided, it will begin the 4-step autonomous process and save the verified results in a `.json` checkpoint file, before generating the final `.pdf` report.
