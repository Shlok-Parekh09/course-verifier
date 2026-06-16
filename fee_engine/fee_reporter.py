import json
import os
import pandas as pd
from datetime import datetime

class FeeReporter:
    def __init__(self, output_dir="fee_reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.results = []
        self.audit_logs = []

    def add_result(self, university, course, url, fee_data, raw_text, screenshot_path):
        """
        fee_data: dict with 'fee_value', 'confidence', 'reasoning'
        """
        record = {
            "University": university,
            "Course": course,
            "URL": url,
            "Extracted_Fee": fee_data.get("fee_value", "Not Found"),
            "Confidence": fee_data.get("confidence", "LOW"),
            "Reasoning": fee_data.get("reasoning", ""),
            "Screenshot": screenshot_path or "N/A"
        }
        self.results.append(record)
        
        audit_record = record.copy()
        audit_record["Raw_Text_Preview"] = raw_text[:500] if raw_text else ""
        audit_record["Timestamp"] = datetime.now().isoformat()
        self.audit_logs.append(audit_record)

        # Periodically save if needed, or wait till the end
        
    def generate_reports(self):
        """Generates Excel and JSON reports."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Excel Report
        df = pd.DataFrame(self.results)
        excel_path = os.path.join(self.output_dir, f"fee_verification_{timestamp}.xlsx")
        df.to_excel(excel_path, index=False)
        print(f"Saved Fee Excel Report to {excel_path}")
        
        # JSON Audit Log
        json_path = os.path.join(self.output_dir, f"fee_audit_logs_{timestamp}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.audit_logs, f, indent=4)
        print(f"Saved Fee Audit Logs to {json_path}")
