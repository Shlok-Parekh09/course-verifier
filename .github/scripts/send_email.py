#!/usr/bin/env python3
import os
import sys
from email_sender import send_report

pdf = os.environ.get("REPORT_PDF", "")
if not pdf:
    # Find the PDF report automatically
    import glob
    pdfs = glob.glob("Verification_Report_Pages_*.pdf")
    if pdfs:
        pdf = pdfs[0]

if pdf and os.path.exists(pdf):
    ok, msg = send_report(
        "Course Verification Complete",
        f"Run finished. Report: {os.path.basename(pdf)}",
        pdf
    )
    print(msg)
    sys.exit(0 if ok else 1)
else:
    print("[!] No report PDF found")
    sys.exit(0)
