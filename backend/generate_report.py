"""
generate_report.py
==================
Generate a PDF report from an existing verification JSON checkpoint.
No browser, no web scraping, no verification — just the PDF.

Usage
-----
  # Interactive (picks JSON, asks for page range)
  python generate_report.py

  # Specify JSON file
  python generate_report.py autonomous_verified_link_compile.pdf.json

  # Specify JSON + page range (start end)
  python generate_report.py autonomous_verified_link_compile.pdf.json 50 100

  # Specify JSON + page range + output name (no .pdf extension)
  python generate_report.py autonomous_verified_link_compile.pdf.json 50 100 my_report
"""

import sys
import os
import glob
import json

# ── Import the AutonomousCourseVerifier class from the main script ──────────
# We only need its generate_pdf_report() method; no browser or API is started.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from autonomous_course_verifier import AutonomousCourseVerifier


def pick_json_file(arg=None):
    """Return the JSON file to load, interactively if needed."""
    if arg and arg.endswith('.json') and os.path.exists(arg):
        return arg

    candidates = sorted(
        glob.glob("autonomous_verified_*.json"),
        key=os.path.getmtime,
        reverse=True
    )
    if not candidates:
        # Also check if user passed a non-standard name
        if arg and os.path.exists(arg):
            return arg
        print("[!] No autonomous_verified_*.json found in the current directory.")
        print("    Pass the JSON file path as the first argument.")
        sys.exit(1)

    print("\n[*] Available verification JSON files:")
    for i, f in enumerate(candidates[:15]):
        size_mb = os.path.getsize(f) / (1024 * 1024)
        print(f"    [{i+1}] {f}  ({size_mb:.1f} MB)")

    choice = input("\n[?] Enter number or full filename (Enter = most recent): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(candidates):
        return candidates[int(choice) - 1]
    elif choice and os.path.exists(choice):
        return choice
    else:
        return candidates[0]


def build_agent(json_file, courses_data):
    """Create a minimal AutonomousCourseVerifier instance without running __init__."""
    base = os.path.basename(json_file)
    if base.startswith("autonomous_verified_") and base.endswith(".json"):
        inferred_source = base[len("autonomous_verified_"):-len(".json")]
    else:
        # Fallback — source name doesn't matter for PDF generation
        inferred_source = base.replace(".json", ".pdf")

    agent = AutonomousCourseVerifier.__new__(AutonomousCourseVerifier)
    agent.pdf_path        = inferred_source
    agent.base_name       = os.path.splitext(os.path.basename(inferred_source))[0]
    agent.output_pdf      = f"autonomous_verified_{agent.base_name}.pdf"
    agent.excel_name      = f"autonomous_verified_{agent.base_name}.xlsx"
    agent.courses         = courses_data
    agent.screenshots_dir = ""
    agent.floating_items  = []
    return agent


def main():
    args = sys.argv[1:]  # [json_file?, start_page?, end_page?, output_name?]

    # ── 1. Pick JSON file ──────────────────────────────────────────────────
    json_file = pick_json_file(args[0] if args else None)
    print(f"\n[*] Loading {json_file} ...")
    with open(json_file, 'r', encoding='utf-8') as f:
        courses_data = json.load(f)
    print(f"    Loaded {len(courses_data)} courses.")

    # ── 2. Build a lightweight agent ───────────────────────────────────────
    agent = build_agent(json_file, courses_data)

    # ── 3. Determine page range ────────────────────────────────────────────
    all_pages = sorted(set(c.get('page_num', 1) for c in agent.courses))
    min_p, max_p = all_pages[0], all_pages[-1]
    print(f"    Pages in data: {min_p} – {max_p}\n")

    # Parse from CLI args (positions after json_file)
    remaining = args[1:]  # [start_page?, end_page?, output_name?]

    if len(remaining) >= 1 and remaining[0].isdigit():
        start_p = int(remaining[0])
    else:
        v = input(f"[?] Start page ({min_p}–{max_p}) [Enter = {min_p}]: ").strip()
        start_p = int(v) if v.isdigit() else min_p

    if len(remaining) >= 2 and remaining[1].isdigit():
        end_p = int(remaining[1])
    else:
        v = input(f"[?] End page ({min_p}–{max_p}) [Enter = {max_p}]: ").strip()
        end_p = int(v) if v.isdigit() else max_p

    # ── 4. Output PDF name ────────────────────────────────────────────────
    if len(remaining) >= 3 and not remaining[2].isdigit():
        pdf_name = remaining[2]
    else:
        default_name = f"report_{agent.base_name}_{start_p}_to_{end_p}"
        v = input(f"[?] Output PDF name (no .pdf) [Enter = {default_name}]: ").strip()
        pdf_name = v if v else default_name

    # ── 5. Convert pages → course indices ────────────────────────────────
    r_start = next(
        (i for i, c in enumerate(agent.courses) if c.get('page_num', 1) >= start_p), 0
    )
    r_end = next(
        (i for i, c in enumerate(agent.courses) if c.get('page_num', 1) > end_p),
        len(agent.courses)
    )

    print(f"\n[*] Generating PDF '{pdf_name}.pdf' ...")
    print(f"    Pages {start_p}–{end_p}  →  courses {r_start + 1} to {r_end} "
          f"({r_end - r_start} courses)")

    # ── 6. Generate ───────────────────────────────────────────────────────
    agent.generate_pdf_report(start_idx=r_start, end_idx=r_end, pdf_name=pdf_name)
    print(f"\n[✓] Done! PDF saved as: {pdf_name}.pdf")


if __name__ == "__main__":
    main()
