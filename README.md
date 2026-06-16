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

### 3. Autonomous Web Verification
- **Anti-Bot Navigation:** Uses `undetected_chromedriver` to bypass bot protections (like Cloudflare).
- **Persistent Sessions:** Saves cookies and sessions in local Chrome profiles to maintain logins for platforms like Coursera and NDU.
- **Smart Scraped Caching:** For specific platforms like NDU, it scrapes multiple course cards in one pass to minimize redundant page loads.

### 4. Local LLM & NLP Engine
- **Hybrid Verification:** Analyzes scraped text against PDF data using local semantic verification.
- **Resilient Routing:** Attempts OpenRouter or Gemini first, with an automatic fallback to **Local Ollama** (e.g., `llama3.2`) or a custom **spaCy NLP engine** if offline.

### 5. Professional Reporting
- **Visual Output:** Generates a detailed PDF report (`_AUTONOMOUS_VERIFIED.pdf`) with color-coded results (matches in green, discrepancies in red).
- **Audit Trail:** Saves screenshots of both the original PDF quadrants and the scraped websites for manual verification.

## 🛠️ Setup & Installation

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/Shlok-Parekh09/course-verifier.git
   cd course-verifier
   ```

2. **Environment Configuration:**
   - Copy `.env.example` to `.env`.
   - Add your API keys (OpenRouter/Gemini) and platform credentials (Coursera/NDU).

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Prepare Data:**
   Ensure `rankings.db` is in the root directory.

## 💻 Usage

Run the main verification engine:
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
