import os
import pandas as pd
from fee_crawler import FeeCrawler
from fee_parser import FeeParser
from fee_verifier import FeeVerifier
from fee_reporter import FeeReporter

class FeeEngine:
    def __init__(self, input_excel="fees.xlsx"):
        self.input_excel = input_excel
        self.crawler = FeeCrawler(headless=True)
        self.parser = FeeParser()
        self.verifier = FeeVerifier()
        self.reporter = FeeReporter()

    def run(self):
        if not os.path.exists(self.input_excel):
            print(f"[Fee Engine] Input file {self.input_excel} not found. Skipping fee extraction.")
            return

        try:
            df = pd.read_excel(self.input_excel)
        except Exception as e:
            print(f"[Fee Engine] Failed to read {self.input_excel}: {e}")
            return

        print(f"[Fee Engine] Found {len(df)} records in {self.input_excel}")

        for index, row in df.iterrows():
            uni_name = str(row.get("University Name", "")).strip()
            course_name = str(row.get("Course Name", "")).strip()
            url = str(row.get("Official Fee URL", "")).strip()

            if not uni_name or not url or pd.isna(url):
                print(f"[Fee Engine] Skipping row {index}: Missing Uni or URL")
                continue

            print(f"--- Processing: {uni_name} - {course_name} ---")
            
            # 1. Crawl
            crawl_result = self.crawler.crawl_fee_page(url, output_dir="fee_reports/screenshots")
            screenshot_path = crawl_result.get("screenshot_path")
            
            # Determine source type
            source_type = "web"
            if crawl_result.get("is_pdf"):
                source_type = "pdf"
                source = url
            elif url.lower().endswith(".docx"):
                source_type = "docx"
                source = url
            elif url.lower().endswith((".png", ".jpg", ".jpeg")):
                source_type = "image"
                source = url
            else:
                source = crawl_result.get("text_content", "")

            # 2. Parse
            raw_text = self.parser.extract_text_from_source(source, source_type=source_type)
            regex_candidates = self.parser.parse_fees(raw_text)
            print(f"   -> Regex Candidates: {regex_candidates}")

            # 3. Verify via LLM
            is_doc = source_type in ["pdf", "image", "docx"]
            fee_data = self.verifier.verify_fee(
                course_name=course_name,
                university_name=uni_name,
                text_content=raw_text,
                regex_candidates=regex_candidates,
                is_pdf_or_ocr=is_doc
            )
            print(f"   -> LLM Verification: {fee_data}")

            # 4. Report
            self.reporter.add_result(
                university=uni_name,
                course=course_name,
                url=url,
                fee_data=fee_data,
                raw_text=raw_text,
                screenshot_path=screenshot_path
            )

        # Generate final outputs
        self.reporter.generate_reports()
        print("[Fee Engine] Processing complete.")

if __name__ == "__main__":
    engine = FeeEngine()
    engine.run()
