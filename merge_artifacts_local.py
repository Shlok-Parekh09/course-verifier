"""
merge_artifacts_local.py
========================
Locally replicates the GitHub Actions 'merge-json' step.

Scans a folder (default: your Downloads folder) for any
  verification-results*.zip
files, extracts only the *link_compile*.json from each zip,
deduplicates by (name, uni, page_num, box_index), sorts by
page_num -> box_index, and writes merged_run.json.

Usage
-----
  # Use default Downloads folder:
  python merge_artifacts_local.py

  # Point at a specific folder that holds the zips:
  python merge_artifacts_local.py --zip-dir "C:/path/to/zips"

  # Also generate PDF report after merging:
  python merge_artifacts_local.py --pdf
"""

import os
import sys
import json
import glob
import zipfile
import argparse
import tempfile
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_ZIP_DIR  = str(Path.home() / "Downloads")
OUTPUT_JSON      = "merged_run.json"
ZIP_PATTERN      = "verification-results*.zip"

# ── Helpers ───────────────────────────────────────────────────────────────────

def find_zips(zip_dir):
    pattern = os.path.join(zip_dir, ZIP_PATTERN)
    zips = sorted(glob.glob(pattern))
    return zips


def extract_link_compile_json(zip_path, tmp_dir):
    """Extract *link_compile*.json entries from a zip into tmp_dir. Returns extracted paths."""
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for entry in zf.namelist():
            basename = os.path.basename(entry)
            if "link_compile" in basename.lower() and basename.lower().endswith(".json"):
                safe_zip = os.path.splitext(os.path.basename(zip_path))[0].replace(" ", "_")
                dest = os.path.join(tmp_dir, f"{safe_zip}__{basename}")
                with zf.open(entry) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                extracted.append(dest)
    return extracted


def merge_jsons(json_paths):
    merged     = []
    seen_keys  = set()
    total_read = 0

    for jf in json_paths:
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"  [!] Error reading {os.path.basename(jf)}: {e}")
            continue

        if not isinstance(data, list):
            print(f"  [!] Skipping {os.path.basename(jf)} (not a JSON array)")
            continue

        added = 0
        total_read += len(data)
        for course in data:
            key = (
                str(course.get("name",     "")).strip().lower(),
                str(course.get("uni",      "")).strip().lower(),
                course.get("page_num"),
                course.get("box_index"),
            )
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(course)
                added += 1

        print(f"  + {os.path.basename(jf)}: {len(data)} entries, {added} new after dedup")

    print(f"\n  Total read across all files : {total_read}")
    print(f"  After deduplication         : {len(merged)}")
    return merged


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Merge verification-results*.zip artifacts -> merged_run.json"
    )
    parser.add_argument(
        "--zip-dir", default=DEFAULT_ZIP_DIR,
        help=f"Folder containing the zip files (default: {DEFAULT_ZIP_DIR})"
    )
    parser.add_argument(
        "--out", default=OUTPUT_JSON,
        help=f"Output JSON filename (default: {OUTPUT_JSON})"
    )
    parser.add_argument(
        "--pdf", action="store_true",
        help="Also generate a PDF report after merging (requires autonomous_course_verifier.py)"
    )
    args = parser.parse_args()

    # 1. Find zips
    print(f"\n[*] Scanning for zips in: {args.zip_dir}")
    zips = find_zips(args.zip_dir)
    if not zips:
        print(f"[!] No files matching '{ZIP_PATTERN}' found in {args.zip_dir}")
        print("    Use --zip-dir to point at the right folder.")
        sys.exit(1)

    print(f"    Found {len(zips)} zip(s):")
    for z in zips:
        size_mb = os.path.getsize(z) / (1024 * 1024)
        print(f"      - {os.path.basename(z)}  ({size_mb:.1f} MB)")

    # 2. Extract link_compile JSONs into a temp folder
    json_paths = []
    with tempfile.TemporaryDirectory(prefix="merge_artifacts_") as tmp_dir:
        print(f"\n[*] Extracting *link_compile*.json from each zip ...")
        for z in zips:
            extracted = extract_link_compile_json(z, tmp_dir)
            if extracted:
                print(f"    {os.path.basename(z)} -> {[os.path.basename(e) for e in extracted]}")
            else:
                print(f"    [!] No link_compile JSON found in {os.path.basename(z)}")
            json_paths.extend(extracted)

        if not json_paths:
            print("\n[!] No link_compile JSON files found across all zips. Aborting.")
            sys.exit(1)

        # Sort so chunks merge in page order (7-46 before 47-86, etc.)
        json_paths.sort()

        # 3. Merge & deduplicate
        print(f"\n[*] Merging {len(json_paths)} JSON file(s) ...")
        merged = merge_jsons(json_paths)

    # 4. Sort by page_num -> box_index (original PDF order)
    merged.sort(key=lambda c: (c.get("page_num", 0), c.get("box_index", 0)))

    # 5. Save output JSON
    out_path = os.path.abspath(args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Saved {len(merged)} courses -> {out_path}")
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"    File size: {size_mb:.2f} MB")

    # 6. Optional PDF generation
    if args.pdf:
        print(f"\n[*] Generating PDF report ...")
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from autonomous_course_verifier import AutonomousCourseVerifier
            agent = AutonomousCourseVerifier.__new__(AutonomousCourseVerifier)
            base = os.path.splitext(args.out)[0]
            agent.pdf_path        = f"{base}.pdf"
            agent.base_name       = base
            agent.output_pdf      = f"{base}.pdf"
            agent.excel_name      = f"{base}.xlsx"
            agent.courses         = merged
            agent.screenshots_dir = ""
            agent.floating_items  = []
            for c in agent.courses:
                if not c.get("processed_this_run", False) and "web_status" in c:
                    c["processed_this_run"] = True
            agent.generate_pdf_report(start_idx=0, end_idx=len(merged), pdf_name=base)
            print(f"[OK] PDF saved -> {base}.pdf")
        except Exception as e:
            print(f"[!] PDF generation failed: {e}")

    print("\nDone!")


if __name__ == "__main__":
    main()
