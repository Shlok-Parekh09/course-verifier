import re
import os
import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image
import docx
import requests
import tempfile

class FeeParser:
    def __init__(self):
        # Broad patterns to catch anything resembling a fee
        self.fee_patterns = [
            r'(?:Rs\.?|INR|₹|USD|\$|EUR|€|GBP|£)\s*[\d,]+(?:\.\d+)?',
            r'[\d,]+(?:\.\d+)?\s*(?:INR|USD|EUR|GBP|Rupees|Dollars)',
            r'(?:Fee|Cost|Price|Tuition).*?(?:Rs\.?|INR|₹|\$)\s*[\d,]+'
        ]

    def _normalize_currency(self, amount_str):
        """Normalizes extracted string to a standard integer/float fee value if possible."""
        clean_str = re.sub(r'[^\d.]', '', amount_str)
        try:
            return float(clean_str)
        except ValueError:
            return None

    def _extract_from_pdf(self, file_path_or_url):
        text = ""
        is_url = file_path_or_url.startswith("http")
        
        try:
            if is_url:
                resp = requests.get(file_path_or_url, timeout=15)
                if resp.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(resp.content)
                        tmp_path = tmp.name
                    with fitz.open(tmp_path) as doc:
                        for page in doc:
                            text += page.get_text() + "\n"
                    os.unlink(tmp_path)
            else:
                with fitz.open(file_path_or_url) as doc:
                    for page in doc:
                        text += page.get_text() + "\n"
        except Exception as e:
            print(f"PDF extraction failed: {e}")
        return text

    def _extract_from_docx(self, file_path):
        text = ""
        try:
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        except Exception as e:
            print(f"DOCX extraction failed: {e}")
        return text

    def _extract_from_image(self, file_path):
        text = ""
        try:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)
        except Exception as e:
            print(f"OCR extraction failed: {e}")
        return text

    def extract_text_from_source(self, source, source_type="web"):
        """
        source: text content if web, otherwise file path or URL
        source_type: 'web', 'pdf', 'docx', 'image'
        """
        if source_type == "web":
            return source
        elif source_type == "pdf":
            return self._extract_from_pdf(source)
        elif source_type == "docx":
            return self._extract_from_docx(source)
        elif source_type == "image":
            return self._extract_from_image(source)
        return ""

    def parse_fees(self, text):
        """
        Extracts candidate fee amounts from text using regex.
        Returns a list of matched fee strings.
        """
        candidates = []
        for pattern in self.fee_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            candidates.extend(matches)
        
        # Deduplicate while preserving order
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)
                
        return unique_candidates

if __name__ == "__main__":
    parser = FeeParser()
    test_text = "The total tuition fee is Rs. 1,50,000 per year. Application fee is ₹500."
    print("Parsed Fees:", parser.parse_fees(test_text))
