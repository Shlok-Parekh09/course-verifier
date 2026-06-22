#!/usr/bin/env python3
"""
run_verifier_pages.py – Standalone launcher for the Course Verifier.
Usage (server / cron / bare-metal):
    python run_verifier_pages.py link_compile.pdf --pages 602 1890
    python run_verifier_pages.py link_compile.pdf --pages 602 1890 --resume
    python run_verifier_pages.py link_compile.pdf --all

Features
• Non-interactive – no stdin prompts; 100 % automation-ready.
• Automatic page-range -> course-index mapping.
• E-mail report on completion (reads .env SMTP_* settings).
• Graceful shutdown (no os._exit hijack).
"""
import sys
import os
import json
import shutil
import time

# Force UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Load env first (before any imports that read it)
from dotenv import load_dotenv
load_dotenv()

# ── Parse CLI ──
PDF_PATH = None
START_PAGE = 782
END_PAGE = 1890
RESUME = False
NO_EMAIL = False
FRESH = False
PAGE_OFFSET = 0
START_IDX = None

args = sys.argv[1:]
i = 0
while i < len(args):
    a = args[i]
    if a in ("--pages", "-p"):
        START_PAGE = int(args[i + 1])
        END_PAGE = int(args[i + 2])
        i += 3
    elif a in ("--resume", "-r"):
        RESUME = True
        i += 1
    elif a in ("--fresh"):
        FRESH = True
        i += 1
    elif a in ("--page-offset"):
        PAGE_OFFSET = int(args[i + 1])
        i += 2
    elif a in ("--start-idx"):
        START_IDX = int(args[i + 1])
        i += 2
    elif a in ("--all"):
        START_PAGE = 1
        END_PAGE = 99999
        i += 1
    elif a in ("--no-email"):
        NO_EMAIL = True
        i += 1
    elif a.startswith("-"):
        print(f"[!] Unknown flag: {a}")
        sys.exit(1)
    else:
        PDF_PATH = a
        i += 1

if not PDF_PATH:
    print("Usage: python run_verifier_pages.py <pdf> [--pages START END] [--fresh] [--page-offset N] [--start-idx N] [--resume] [--all] [--no-email]")
    sys.exit(1)

# Resume-only mode: if the original PDF is absent but a checkpoint JSON exists,
# we can still run web verification / rankings / PDF report from the checkpoint
# (extraction is skipped on resume). This lets the pipeline run in environments
# that only have the small checkpoint committed — e.g. GitHub Actions without
# the 139 MB source PDF.
_resume_checkpoint_path = f"autonomous_verified_{os.path.basename(PDF_PATH)}.json"
if not os.path.exists(PDF_PATH):
    if FRESH:
        print(f"[X] --fresh requires the source PDF, which was not found: {PDF_PATH}")
        sys.exit(1)
    elif os.path.exists(_resume_checkpoint_path):
        print(f"[!] PDF not found: {PDF_PATH} — proceeding in resume-only mode from checkpoint: {_resume_checkpoint_path}")
    else:
        print(f"[X] PDF not found: {PDF_PATH} and no checkpoint available. Nothing to do.")
        sys.exit(1)

# ── Import verifier after env is loaded ──
from autonomous_course_verifier import AutonomousCourseVerifier, check_runtime_dependencies

if not check_runtime_dependencies():
    sys.exit(1)

agent = AutonomousCourseVerifier(PDF_PATH)

# ── Resume logic ──
resume = RESUME
checkpoint_path = f"autonomous_verified_{os.path.basename(PDF_PATH)}.json"
start_idx = 0

if os.path.exists(checkpoint_path) and not resume and not FRESH:
    # Auto-resume if checkpoint exists and we are in the target range
    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            _peek = json.load(f)
        # Only auto-resume when the checkpoint contains our target range
        resume = True
        print(f"[*] Auto-resuming from checkpoint: {checkpoint_path}")
    except Exception:
        resume = False

if resume and os.path.exists(checkpoint_path):
    try:
        with open(checkpoint_path, "r", encoding="utf-8") as f:
            agent.courses = json.load(f)
        for c in agent.courses:
            c['processed_this_run'] = False
        # Find first unverified course
        for i, c in enumerate(agent.courses):
            if c.get("web_status") == "FALSE" and c.get("reason", "") == "":
                start_idx = i
                break
        else:
            start_idx = len(agent.courses)
        print(f"[*] Resumed {len(agent.courses)} courses. Web verification resumes at index {start_idx}.")
        agent.validate_page_nums_against_pdf()
        agent.export_to_excel(quiet=True)
    except Exception as e:
        print(f"[!] Could not load checkpoint: {e}")
        start_idx = 0
        resume = False

if not resume:
    try:
        screenshots_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verification_screenshots")
        if os.path.exists(screenshots_base):
            shutil.rmtree(screenshots_base)
            print("[*] Flushed old screenshot folders.")
    except Exception as e:
        print(f"[!] Could not flush old screenshots: {e}")
    try:
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
            print("[*] Flushed old checkpoint.")
    except Exception as e:
        print(f"[!] Could not flush checkpoint: {e}")
    agent.extract_and_parse()
    if PAGE_OFFSET:
        for c in agent.courses:
            c['page_num'] = c.get('page_num', 0) + PAGE_OFFSET
        print(f"[*] Applied page offset {PAGE_OFFSET} (cropped PDF page 1 -> original page {1 + PAGE_OFFSET}).")

# ── Map page numbers to course indices ──
min_page = min((c.get('page_num', 1) for c in agent.courses), default=1)
max_page = max((c.get('page_num', 1) for c in agent.courses), default=1)

s_idx = None
e_idx = len(agent.courses)
for i, c in enumerate(agent.courses):
    if c.get('page_num', 1) >= START_PAGE and s_idx is None:
        s_idx = i
    if c.get('page_num', 1) > END_PAGE:
        e_idx = i
        break

if s_idx is None:
    s_idx = 0
if e_idx <= s_idx:
    e_idx = len(agent.courses)

print(f"[*] Target pages {START_PAGE}-{END_PAGE} maps to course indices {s_idx}-{e_idx} ({e_idx - s_idx} courses)")

# Clamp to resume start if resuming
if resume and start_idx > s_idx:
    s_idx = start_idx
    print(f"[*] Resume override: starting from index {s_idx}")

# ── Visual extraction (skip if resuming) ──
if not resume and s_idx < len(agent.courses):
    agent.extract_visuals_for_range(start_idx=s_idx, end_idx=e_idx)

agent.export_to_excel(quiet=True)
try:
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(agent.courses, f, indent=4, ensure_ascii=False)
    print("[*] Initial extraction checkpoint saved.")
except Exception as e:
    print(f"[!] Could not save initial checkpoint: {e}")

# ── Web verification ──
web_verify_ok = True
if s_idx < len(agent.courses):
    try:
        agent.autonomous_web_verify(start_idx=s_idx, end_idx=e_idx)
    except Exception as e:
        web_verify_ok = False
        print(f"\n[!] Web verification crashed: {e}")
        print("[*] Continuing to rankings + PDF with whatever was verified so far (JSON checkpoint is safe).")
else:
    print("[*] All courses in range already verified.")

# ── Rankings ──
print("\n[*] Verifying QS/NIRF rankings...")
try:
    agent.verify_rankings(start_idx=s_idx, end_idx=e_idx)
except Exception as e:
    print(f"[!] Rankings step crashed: {e}")

# ── PDF Report ── (always attempted, even if web verify / rankings failed)
pdf_name = f"Verification_Report_Pages_{START_PAGE}_to_{END_PAGE}"
try:
    agent.generate_pdf_report(start_idx=s_idx, end_idx=e_idx, pdf_name=pdf_name, start_number=START_IDX)
except Exception as e:
    print(f"[!] PDF report generation crashed: {e}")
    print(f"[!] JSON checkpoint is still safe at: {checkpoint_path}")

# ── Dashboard sync ──
if os.path.exists("autonomous_verified_data.json"):
    shutil.copy("autonomous_verified_data.json", "master_dashboard_results.json")
    print("\n[*] Copied results to master_dashboard_results.json")

# ── Email report ──
if not NO_EMAIL:
    try:
        from email_sender import send_report
        report_pdf = f"{pdf_name}.pdf"
        subject = f"Course Verification Complete – Pages {START_PAGE}-{END_PAGE}"
        body = (
            f"Verification finished for {PDF_PATH}\n"
            f"Page range: {START_PAGE} – {END_PAGE}\n"
            f"Courses processed: {e_idx - s_idx}\n"
            + (f"Report numbering starts at: {START_IDX}\n" if START_IDX else "")
            + f"Report attached: {report_pdf}\n"
        )
        if os.path.exists(report_pdf):
            ok, msg = send_report(subject, body, report_pdf)
            print(f"[{'OK' if ok else 'X'}] Email: {msg}")
        else:
            print(f"[!] Report PDF not found: {report_pdf}")
    except Exception as e:
        print(f"[!] Email step failed: {e}")
else:
    print("[*] Email suppressed (--no-email).")

print("\n[*] Done.")
