"""
consensus_merger.py
===================
Merge 5 verifier JSON runs of the 3727-course collection using a 4-out-of-5
majority rule for every boolean field, then generate a PDF that looks
IDENTICAL to the main workflow output.

Usage
-----
  # Pass 5 JSON files as arguments:
  python consensus_merger.py run1.json run2.json run3.json run4.json run5.json

  # Optional: specify output PDF name (no .pdf extension):
  python consensus_merger.py run1.json run2.json run3.json run4.json run5.json --out merged_report

  # Interactive mode (prompts for each file):
  python consensus_merger.py

How It Works
------------
  1. Loads all 5 JSON files.
  2. Matches courses across files by (name + uni) key, falling back to index.
  3. For every boolean field: if True appears >= 4 times -> merged = True.
  4. For web_status ("TRUE"/"FALSE"/"MATCH"): same 4/5 rule.
  5. For string fields: picks from the file where processed_this_run=True,
     preferring the most informative (non-empty) value.
  6. Saves merged_consensus.json.
  7. Calls generate_pdf_report() from autonomous_course_verifier.py -
     producing a PDF identical in format to the main workflow output.
"""

import sys
import os
import json
import argparse
from collections import Counter

# Re-use the existing PDF generation pipeline
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from autonomous_course_verifier import AutonomousCourseVerifier

# ── Constants ─────────────────────────────────────────────────────────────────

THRESHOLD = 4  # need at least this many "true" votes out of 5

# All boolean fields in the JSON schema
BOOLEAN_FIELDS = [
    "has_qs_badge",
    "has_nirf_badge",
    "has_free_box",
    "has_scholarship_box",
    "qs_ranked",
    "nirf_ranked",
    "scholarship_found",
    "logo_match",
    "country_match",
    "direct_link_working",
    "cost_match",
    "duration_match",
    "mode_match",
    "lang_match",
    "sk_match",
    "uni_match",
    "has_logos",
    "is_hard_error",
]

# web_status is stored as string "TRUE" / "FALSE" / "MATCH" - treat as boolean
BOOL_STRING_FIELDS = ["web_status"]

# String fields picked from the "best" run rather than voted on
STRING_FIELDS = [
    "reason", "issue_category", "issue_sub_type",
    "web_name", "web_cost", "web_uni", "skills_verified",
    "qs_detail", "nirf_detail", "language", "fee_url",
    "logos_found", "country_verified", "web_duration",
    "web_mode", "web_language", "url",
    "name", "uni", "cost", "duration", "skills", "mode", "country", "domain",
]

# Fields copied verbatim from run[0] (reference) - positional metadata
IDENTITY_FIELDS = [
    "page_num", "box_position", "box_index",
    "retry_count", "error_screenshot_path",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_key(course):
    name = str(course.get("name", "")).strip().lower()
    uni  = str(course.get("uni",  "")).strip().lower()
    return f"{name}|||{uni}"


def load_json(path):
    print(f"  [+] Loading: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"      -> {len(data)} courses loaded.")
    return data


def bool_val(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().upper() in ("TRUE", "1", "YES", "MATCH")
    return bool(v)


def consensus_bool(values, threshold=None):
    if threshold is None:
        threshold = THRESHOLD
    return sum(1 for v in values if bool_val(v)) >= threshold


def bool_string_consensus(values, threshold=None):
    if threshold is None:
        threshold = THRESHOLD
    match_count = sum(1 for v in values if str(v).strip().upper() == "MATCH")
    true_count  = sum(1 for v in values if str(v).strip().upper() in ("TRUE", "MATCH"))
    if match_count >= threshold:
        return "MATCH"
    if true_count >= threshold:
        return "TRUE"
    return "FALSE"


def best_string(field, slots, ref_course):
    candidates = []
    for c in slots:
        v = c.get(field, "")
        if v is None:
            v = ""
        v = str(v).strip()
        if v and v.lower() not in ("", "none", "nan", "n/a"):
            candidates.append((v, bool(c.get("processed_this_run", False))))

    processed_vals = [v for v, proc in candidates if proc]
    if processed_vals:
        return max(processed_vals, key=len)

    if candidates:
        counts = Counter(v for v, _ in candidates)
        return counts.most_common(1)[0][0]

    return ref_course.get(field, "")


# ── Core merge logic ──────────────────────────────────────────────────────────

def merge_courses(all_runs):
    n_runs = len(all_runs)
    print(f"\n[*] Merging {n_runs} runs ...")

    run_dicts = []
    for run in all_runs:
        d = {}
        for c in run:
            k = make_key(c)
            if k not in d:
                d[k] = c
        run_dicts.append(d)

    reference_run = all_runs[0]
    merged = []
    stats = {f: {"changed": 0} for f in BOOLEAN_FIELDS + BOOL_STRING_FIELDS}

    for idx, ref_course in enumerate(reference_run):
        key = make_key(ref_course)

        slots = []
        for ri, rd in enumerate(run_dicts):
            if key in rd:
                slots.append(rd[key])
            elif idx < len(all_runs[ri]):
                slots.append(all_runs[ri][idx])
            else:
                slots.append(ref_course)

        mc = {}

        # Identity fields from reference
        for f in IDENTITY_FIELDS:
            mc[f] = ref_course.get(f)

        # Boolean consensus
        for f in BOOLEAN_FIELDS:
            values = [s.get(f, False) for s in slots]
            result = consensus_bool(values)
            mc[f] = result
            if bool_val(ref_course.get(f, False)) != result:
                stats[f]["changed"] += 1

        # String-boolean consensus
        for f in BOOL_STRING_FIELDS:
            values = [s.get(f, "FALSE") for s in slots]
            result = bool_string_consensus(values)
            mc[f] = result
            if str(ref_course.get(f, "FALSE")).upper() != result:
                stats[f]["changed"] += 1

        # String fields - best value
        for f in STRING_FIELDS:
            mc[f] = best_string(f, slots, ref_course)

        # processed_this_run: True if ANY run processed it
        mc["processed_this_run"] = any(s.get("processed_this_run", False) for s in slots)

        # Carry over any extra fields not explicitly handled
        for f, v in ref_course.items():
            if f not in mc:
                mc[f] = v

        merged.append(mc)

    print("\n  [*] Consensus change report (differs from run #1):")
    any_changes = False
    for f in BOOLEAN_FIELDS + BOOL_STRING_FIELDS:
        ch = stats[f]["changed"]
        if ch > 0:
            print(f"      {f:<30} -> {ch:>5} courses changed")
            any_changes = True
    if not any_changes:
        print("      (No boolean fields changed - all 5 runs agree.)")

    return merged


# ── PDF generation ────────────────────────────────────────────────────────────

def build_agent(courses, output_name):
    agent = AutonomousCourseVerifier.__new__(AutonomousCourseVerifier)
    agent.pdf_path        = f"{output_name}.pdf"
    agent.base_name       = output_name
    agent.output_pdf      = f"{output_name}.pdf"
    agent.excel_name      = f"{output_name}.xlsx"
    agent.courses         = courses
    agent.screenshots_dir = ""
    agent.floating_items  = []
    return agent


# ── Interactive file picker ───────────────────────────────────────────────────

def prompt_json_files(n=5):
    import glob
    candidates = sorted(
        glob.glob("autonomous_verified_*.json") + glob.glob("*.json"),
        key=os.path.getmtime,
        reverse=True
    )[:20]

    if candidates:
        print("\n[*] JSON files found in the current directory:")
        for i, f in enumerate(candidates):
            size_mb = os.path.getsize(f) / (1024 * 1024)
            print(f"    [{i+1:>2}] {f}  ({size_mb:.1f} MB)")

    files = []
    for i in range(1, n + 1):
        while True:
            choice = input(f"\n[?] File #{i} — enter number or full path: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                files.append(candidates[int(choice) - 1])
                break
            elif choice and os.path.exists(choice):
                files.append(choice)
                break
            else:
                print(f"    [!] Not found: {choice!r} — try again.")
    return files


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Merge 5 verifier JSON runs (4/5 consensus) -> merged JSON + PDF."
    )
    parser.add_argument(
        "files", nargs="*",
        help="5 JSON file paths. Omit for interactive mode."
    )
    parser.add_argument(
        "--out", default="merged_consensus",
        help="Output base name (no extension). Default: merged_consensus"
    )
    parser.add_argument(
        "--threshold", type=int, default=4,
        help="Minimum votes for a boolean to be True (default: 4 of 5)."
    )
    args = parser.parse_args()

    global THRESHOLD
    THRESHOLD = args.threshold

    # 1. Collect file paths
    if len(args.files) == 5:
        json_paths = args.files
    elif len(args.files) > 0:
        print(f"[!] Need exactly 5 files, got {len(args.files)}. Switching to interactive.\n")
        json_paths = prompt_json_files(5)
    else:
        json_paths = prompt_json_files(5)

    # 2. Validate
    for p in json_paths:
        if not os.path.exists(p):
            print(f"[!] File not found: {p}")
            sys.exit(1)

    # 3. Load
    print(f"\n[*] Loading {len(json_paths)} JSON files ...")
    all_runs = [load_json(p) for p in json_paths]
    sizes = [len(r) for r in all_runs]
    print(f"\n    Course counts per file: {sizes}")
    if len(set(sizes)) > 1:
        print("    [!] WARNING: Files have different course counts.")
        print("        Merging by (name+uni) key with positional fallback.")

    # 4. Merge
    merged = merge_courses(all_runs)
    print(f"\n[*] Merged total: {len(merged)} courses.")

    # 5. Save JSON
    out_json = f"{args.out}.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"[*] Saved: {out_json}")

    # 6. Generate PDF (same format as main workflow)
    print(f"\n[*] Generating PDF: {args.out}.pdf ...")
    agent = build_agent(merged, args.out)

    # Ensure every course with web_status is included in the PDF output
    for c in agent.courses:
        if not c.get("processed_this_run", False) and "web_status" in c:
            c["processed_this_run"] = True

    agent.generate_pdf_report(start_idx=0, end_idx=len(merged), pdf_name=args.out)

    print(f"\n[✓] All done!")
    print(f"    JSON : {out_json}")
    print(f"    PDF  : {args.out}.pdf")


if __name__ == "__main__":
    main()
