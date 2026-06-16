import json
import sys
import os

# Add parent dir to path so we can import llm_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm_manager import get_llm_manager

class FeeVerifier:
    def __init__(self):
        self.llm = get_llm_manager()

    def verify_fee(self, course_name, university_name, text_content, regex_candidates, is_pdf_or_ocr=False):
        """
        Uses LLM to verify and extract the exact fee for the given course.
        """
        system_prompt = (
            "You are an expert educational data extractor. "
            "Your job is to find the exact tuition fee or total cost for a specific course at a university. "
            "Return JSON only with keys: 'fee_value' (string with currency), 'confidence' (HIGH, MEDIUM, LOW), and 'reasoning' (brief string)."
        )
        
        # Truncate text to avoid blowing up the context window
        text_preview = text_content[:15000] if text_content else "No text provided."

        prompt = (
            f"University: {university_name}\n"
            f"Course: {course_name}\n"
            f"Regex Found Candidates: {regex_candidates}\n\n"
            f"Page/Document Text:\n{text_preview}\n\n"
            "Extract the official fee. If multiple are listed (e.g., per semester vs per year), prefer the total or annual fee and specify it. "
            "If no fee is found, set 'fee_value' to 'Not Found' and 'confidence' to 'LOW'."
            "If the text is from OCR/PDF and seems messy, lower the confidence slightly unless the fee is extremely clear."
        )

        try:
            res = self.llm.generate(prompt=prompt, system=system_prompt, format="json", temperature=0.1)
            if res:
                data = json.loads(res)
                # Adjust confidence if OCR/PDF
                if is_pdf_or_ocr and data.get("confidence") == "HIGH":
                    data["confidence"] = "MEDIUM" # be slightly more conservative with OCR
                return data
        except Exception as e:
            print(f"Fee LLM Verification failed: {e}")
            
        return {
            "fee_value": "Error",
            "confidence": "LOW",
            "reasoning": "LLM extraction failed."
        }
