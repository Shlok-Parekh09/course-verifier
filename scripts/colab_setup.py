#!/usr/bin/env python3
"""
Run Course Verifier on Google Colab (FREE)
================================================
This script is meant to be COPY-PASTED into Colab cells.
For a ready-made notebook file, use: notebooks/verifier_colab.ipynb

Steps:
1. Open https://colab.research.google.com
2. File → Upload notebook → Select notebooks/verifier_colab.ipynb
3. Upload link_compile.pdf to the Colab Files panel (left sidebar)
4. Upload your .env file (with API keys and SMTP settings)
5. Run cells top to bottom
6. Wait — Colab stays alive up to 12 hours. Report will be emailed.
"""

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CELL 1: Mount Google Drive (optional but recommended)           ║
# ╚══════════════════════════════════════════════════════════════════╝
from google.colab import drive
drive.mount('/content/drive')
# Now you can store results in /content/drive/MyDrive/verifier_output/

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CELL 2: Clone repo & install dependencies                       ║
# ╚══════════════════════════════════════════════════════════════════╝
import os, subprocess

REPO_URL = "https://github.com/Shlok-Parekh09/course-verifier.git"
BRANCH   = "yug-render-deploy"
WORKDIR  = "/content/course-verifier"

# Clone
if not os.path.exists(WORKDIR):
    subprocess.run(["git", "clone", "-b", BRANCH, REPO_URL, WORKDIR], check=True)
os.chdir(WORKDIR)

# Install system deps (Colab is Ubuntu-based)
!apt-get update -qq
!apt-get install -y -qq wget gnupg2 ca-certificates fonts-liberation libglib2.0-0 libnss3 libgconf-2-4 libfontconfig1 libxss1 libappindicator3-1 libatk-bridge2.0-0 libgtk-3-0 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 libxrandr2 libasound2 libpangocairo-1.0-0 libatspi2.0-0 libcups2 libdrm2 libgbm1 libxkbcommon0 tesseract-ocr tesseract-ocr-eng unzip curl

# Install Chrome
!wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
!echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list
!apt-get update -qq && apt-get install -y -qq google-chrome-stable

# Python deps
!pip install -q -r requirements.txt
!playwright install chromium || true

print("Setup complete!")

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CELL 3: Copy uploaded files into workspace                       ║
# ╚══════════════════════════════════════════════════════════════════╝
import shutil

upload_root = "/content"
for fname in ['link_compile.pdf', '.env']:
    src = os.path.join(upload_root, fname)
    dst = os.path.join(WORKDIR, fname)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy(src, dst)
        print(f"Copied {fname}")

assert os.path.exists("link_compile.pdf"), "Upload link_compile.pdf via the Files panel!"
assert os.path.exists(".env"), "Upload .env via the Files panel!"
print("PDF and .env detected. Ready to run.")

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CELL 4: Run the verifier                                         ║
# ╚══════════════════════════════════════════════════════════════════╝
import os

START_PAGE = 602
END_PAGE   = 1890
BROWSERS   = 2

os.environ["VERIFIER_NO_FORCE_EXIT"] = "true"

# Patch browser count
with open("autonomous_course_verifier.py", "r", encoding="utf-8") as f:
    src = f.read()
src = src.replace("NUM_BROWSERS = 6", f"NUM_BROWSERS = {BROWSERS}")
with open("autonomous_course_verifier.py", "w", encoding="utf-8") as f:
    f.write(src)

!python run_verifier_pages.py link_compile.pdf --pages {START_PAGE} {END_PAGE} --no-email
print("Verifier finished!")

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CELL 5: Email the report                                         ║
# ╚══════════════════════════════════════════════════════════════════╝
import glob
from email_sender import send_report

pdfs = glob.glob("Verification_Report_Pages_*.pdf")
if pdfs:
    pdf = pdfs[0]
    ok, msg = send_report(
        f"Course Verification Complete — Pages {START_PAGE}-{END_PAGE}",
        f"Colab run finished.\nPage range: {START_PAGE} – {END_PAGE}\nReport: {os.path.basename(pdf)}",
        pdf
    )
    print(f"[{'OK' if ok else 'FAIL'}] Email: {msg}")
else:
    print("No PDF report found.")

# ╔══════════════════════════════════════════════════════════════════╗
# ║  CELL 6: Save results to Google Drive (optional)                  ║
# ╚══════════════════════════════════════════════════════════════════╝
import datetime, glob

outdir = f"/content/drive/MyDrive/verifier_output/{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.makedirs(outdir, exist_ok=True)

for pattern in ["*.xlsx", "Verification_Report_Pages_*.pdf", "autonomous_verified_link_compile.pdf.json"]:
    for f in glob.glob(pattern):
        if os.path.exists(f):
            shutil.copy(f, outdir)
            print(f"Saved: {f}")

print("Done! Check your Google Drive under verifier_output/")
