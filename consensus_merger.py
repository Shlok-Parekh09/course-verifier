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

# AI-review verdicts with confidence above this ceiling are considered
# sufficiently certain that no AI fields are written back to the course.
AI_REVIEW_WRITE_MAX = 0.75

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

# Categorical string fields that should be chosen by majority vote, not by length.
CATEGORICAL_FIELDS = {
    "issue_category",
    "issue_sub_type",
}

# Free-text string fields where we prefer the most informative processed value.
STRING_FIELDS = [
    "reason",
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

def _first_non_empty(*values):
    """Return the first non-empty string value, or empty string."""
    for v in values:
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return ""


def make_key(course):
    name = str(course.get("name", "")).strip().lower()
    # Different verifier outputs use either 'uni' (newer schema) or
    # 'university' (older schema). Try both so the same course matches.
    uni = _first_non_empty(course.get("uni"), course.get("university")).lower()
    # Append domain when name+uni is empty so completely empty courses still
    # have a (poor but distinct) key instead of colliding at "|||".
    if not name and not uni:
        domain = str(course.get("domain", "")).strip().lower()
        return f"|||{domain}"
    return f"{name}|||{uni}"


def normalize_course(course):
    """Make variant schemas compatible with the merger's expected keys."""
    # Older outputs store the institute under 'university' instead of 'uni'.
    if not str(course.get("uni", "")).strip() and course.get("university"):
        course["uni"] = course["university"]
    return course


def load_json(path):
    print(f"  [+] Loading: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of courses, got {type(data).__name__}")
    data = [c for c in data if c is not None]
    print(f"      -> {len(data)} courses loaded.")
    return [normalize_course(c) for c in data]


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


def _plausible_value(v):
    """Return True if v looks like a real, non-placeholder string value."""
    if v is None:
        return False
    s = str(v).strip()
    return s and s.lower() not in ("", "none", "nan", "n/a")


def best_string(field, slots, ref_course):
    """Pick the best free-text value from the runs that processed the course."""
    candidates = []
    for c in slots:
        v = c.get(field, "")
        if _plausible_value(v):
            candidates.append((str(v).strip(), bool(c.get("processed_this_run", False))))

    processed_vals = [v for v, proc in candidates if proc]
    if processed_vals:
        # Prefer the longest non-empty processed value (more informative),
        # but break ties deterministically by alphabetical order.
        return max(sorted(processed_vals), key=len)

    if candidates:
        counts = Counter(v for v, _ in candidates)
        return counts.most_common(1)[0][0]

    return ref_course.get(field, "")


def consensus_string(field, slots, ref_course):
    """Choose a categorical string by majority vote across all runs.

    Falls back to the reference value if every run is missing the field.
    """
    values = []
    for c in slots:
        v = c.get(field)
        if _plausible_value(v):
            values.append(str(v).strip())

    if values:
        counts = Counter(values)
        # Tie-break by preferring the value from the most processed runs, then
        # by alphabetical order for deterministic output.
        max_count = max(counts.values())
        top = [v for v, cnt in counts.items() if cnt == max_count]
        if len(top) == 1:
            return top[0]
        # Tie-break: which top value appears more often in processed runs?
        processed_counts = Counter()
        for c in slots:
            v = c.get(field)
            if _plausible_value(v) and c.get("processed_this_run"):
                processed_counts[str(v).strip()] += 1
        best_top = max(top, key=lambda v: (processed_counts.get(v, 0), v))
        return best_top

    return ref_course.get(field, "")


# ── Core merge logic ──────────────────────────────────────────────────────────

def _build_run_lookups(all_runs):
    """Build per-run occurrence-aware lookup structures.

    Each run is represented as a dict mapping (key, occurrence_index) to the
    course object, plus a plain key->first-occurrence fallback. This preserves
    genuinely different courses that share the same (name+uni) key.
    """
    lookups = []
    duplicate_keys_total = 0
    for run in all_runs:
        key_to_occurrences = {}
        first_occurrence = {}
        seen_count = {}
        for c in run:
            k = make_key(c)
            occ = seen_count.get(k, 0)
            seen_count[k] = occ + 1
            key_to_occurrences.setdefault(k, []).append((occ, c))
            if occ == 0:
                first_occurrence[k] = c
            else:
                duplicate_keys_total += 1
        lookups.append({
            "by_key_occ": {(k, occ): c for k, occurrences in key_to_occurrences.items() for occ, c in occurrences},
            "first_occurrence": first_occurrence,
            "seen_count": seen_count,
        })
    return lookups, duplicate_keys_total


def merge_courses(all_runs, warn_on_duplicate_keys=True):
    n_runs = len(all_runs)
    print(f"\n[*] Merging {n_runs} runs ...")

    # Build occurrence-aware lookups so duplicate (name+uni) groups are kept
    # distinct instead of collapsing to the first occurrence.
    lookups, duplicate_keys_total = _build_run_lookups(all_runs)

    if warn_on_duplicate_keys and duplicate_keys_total:
        print(f"    [!] {duplicate_keys_total} duplicate (name+uni) keys found across runs; "
              f"occurrence-aware matching is used to keep them distinct.")

    reference_run = all_runs[0]
    ref_lookup = lookups[0]

    # Precompute occurrence number for every course in the reference run.
    ref_occurrence = []
    seen_so_far = {}
    for c in reference_run:
        k = make_key(c)
        ref_occurrence.append(seen_so_far.get(k, 0))
        seen_so_far[k] = seen_so_far.get(k, 0) + 1

    merged = []
    stats = {f: {"changed": 0} for f in BOOLEAN_FIELDS + BOOL_STRING_FIELDS}

    for idx, ref_course in enumerate(reference_run):
        key = make_key(ref_course)
        occ = ref_occurrence[idx]

        slots = []
        for ri, lu in enumerate(lookups):
            if (key, occ) in lu["by_key_occ"]:
                slots.append(lu["by_key_occ"][(key, occ)])
            elif key in lu["first_occurrence"]:
                # Key exists but occurrence count differs; fallback to first
                # occurrence so we still get same-course data rather than index.
                slots.append(lu["first_occurrence"][key])
            elif idx < len(all_runs[ri]):
                # Positional fallback
                slots.append(all_runs[ri][idx])
            else:
                # Run is shorter than the reference; duplicate ref_course values
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

        # Categorical fields - majority vote
        for f in CATEGORICAL_FIELDS:
            mc[f] = consensus_string(f, slots, ref_course)

        # Free-text string fields - best informative value
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
    # generate_pdf_report references these attributes; give them safe defaults.
    agent.screenshots_dir = ""
    agent.floating_items  = []
    agent.input_pdf       = f"{output_name}.pdf"
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


# ── AI trust layer (Ollama) ───────────────────────────────────────────────────

# Fields the AI reviewer should focus on when the 5 runs disagree.
_AI_REVIEW_FIELDS = [
    "cost_match", "duration_match", "mode_match", "lang_match",
    "sk_match", "uni_match", "country_match", "direct_link_working",
]


def collect_split_votes(merged, all_runs):
    """Return merged courses where the 5 runs disagreed on important fields.

    Uses the same occurrence-aware matching as merge_courses so duplicate
    (name+uni) groups are reviewed against their correct counterparts.
    """
    lookups, _ = _build_run_lookups(all_runs)

    # Precompute reference-run occurrence numbers.
    ref_seen = {}
    ref_occurrence = []
    for c in all_runs[0]:
        k = make_key(c)
        ref_occurrence.append(ref_seen.get(k, 0))
        ref_seen[k] = ref_seen.get(k, 0) + 1

    borderline = []
    for idx, mc in enumerate(merged):
        key = make_key(mc)
        occ = ref_occurrence[idx]

        slots = []
        for lu in lookups:
            if (key, occ) in lu["by_key_occ"]:
                slots.append(lu["by_key_occ"][(key, occ)])
            elif key in lu["first_occurrence"]:
                slots.append(lu["first_occurrence"][key])
            elif idx < len(all_runs[len(slots)]):
                slots.append(all_runs[len(slots)][idx])
            else:
                slots.append({})

        votes = {}

        # web_status is the most important aggregate signal
        ws_votes = Counter(
            str(s.get("web_status", "FALSE")).strip().upper()
            for s in slots if s.get("web_status")
        )
        if len(ws_votes) > 1:
            votes["web_status"] = dict(ws_votes)

        # boolean match fields
        for f in _AI_REVIEW_FIELDS:
            cnt = Counter(bool(s.get(f, False)) for s in slots)
            if len(cnt) > 1:
                votes[f] = {str(k): v for k, v in cnt.items()}

        if not votes:
            continue

        # Collect up to 5 distinct, non-empty reason snippets
        reasons = []
        for s in slots:
            r = str(s.get("reason", "")).strip()
            if r and r not in reasons:
                reasons.append(r[:300])
                if len(reasons) >= 5:
                    break

        borderline.append({
            "idx": idx,
            "name": str(mc.get("name", "")),
            "uni": str(mc.get("uni", "")),
            "url": str(mc.get("url", "")),
            "consensus_web_status": str(mc.get("web_status", "FALSE")),
            "votes": votes,
            "reasons": reasons,
        })

    return borderline


def build_ai_prompt(batch):
    """Build a JSON-mode prompt asking Ollama to review a batch of split-vote courses."""
    prompt = (
        "You are a strict data-quality reviewer for a course verification system. "
        "Five independent runs verified the same course catalog. The list below contains "
        "courses where the runs disagreed. For each course, review the vote tallies and "
        "the conflicting reason snippets, then judge whether the merged consensus result "
        "is trustworthy.\n\n"
        "Return ONLY a raw JSON object. Do NOT add markdown code fences (no ```json), "
        "no explanations, and no text outside the JSON. The output must be valid JSON "
        "that Python's json.loads() can parse directly.\n\n"
        "Map each course index (the integer \"idx\" value) to an object with exactly these keys:\n"
        "  - \"confidence\": float between 0.0 and 1.0\n"
        "  - \"status\": one of \"AGREE\", \"DISAGREE\", or \"REVIEW\"\n"
        "  - \"note\": a single concise sentence explaining the verdict\n\n"
        "Example shape for one course:\n"
        '{"0": {"confidence": 0.65, "status": "REVIEW", "note": "Mixed votes on web_status and cost_match make the consensus uncertain."}}\n\n'
        "Courses:\n"
    )
    prompt += json.dumps(batch, ensure_ascii=False, indent=2)
    prompt += "\n\nReturn raw JSON:"
    return prompt


def _parse_ai_json(raw):
    """Try several strategies to extract a JSON object from the model output."""
    if not raw:
        return None
    text = raw.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. Strip markdown code fences
    import re
    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # 3. Look for the first { ... } object in the text
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass

    # 4. Try to repair common single-quote mistakes
    try:
        repaired = text.replace("'", '"')
        return json.loads(repaired)
    except Exception:
        pass

    return None


def call_ollama_review(batch, demo=False):
    """Send one batch to Ollama (with Google AI Studio fallback) and return results."""
    if demo:
        return {
            str(item["idx"]): {
                "confidence": 0.55,
                "status": "REVIEW",
                "note": "Demo mode: AI review code path is active (no Ollama call was made).",
            }
            for item in batch
        }

    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from llm_manager import get_llm_manager
        mgr = get_llm_manager()
    except Exception as e:
        print(f"    [!] Could not initialize LLM manager: {e}")
        return {}

    prompt = build_ai_prompt(batch)
    raw = mgr.generate(prompt, format="json", temperature=0.0)
    if raw:
        parsed = _parse_ai_json(raw)
        if parsed is not None:
            return parsed
        print("    [!] Could not parse LLM JSON response; batch will be retried once.")
    else:
        print("    [!] LLM AI review returned empty response; retrying batch once.")

    # One explicit retry (model fallbacks already happened inside generate())
    raw = mgr.generate(prompt, format="json", temperature=0.0)
    if raw:
        parsed = _parse_ai_json(raw)
        if parsed is not None:
            return parsed
        print("    [!] Could not parse LLM JSON response on retry.")
    else:
        print("    [!] LLM AI review returned empty response on retry.")
    return {}


def _clamp_confidence(v):
    """Return confidence as a float in [0.0, 1.0]; invalid values become 0.0."""
    try:
        c = float(v)
    except (TypeError, ValueError):
        return 0.0
    if c < 0.0:
        return 0.0
    if c > 1.0:
        return 1.0
    return c


def attach_ai_results(merged, ai_results, threshold=0.5):
    """Write AI review fields back into the merged course list.

    Courses whose AI confidence is greater than AI_REVIEW_WRITE_MAX do not
    receive any AI review annotation (no field is written).
    """
    written = 0
    valid_statuses = {"AGREE", "DISAGREE", "REVIEW"}
    for idx_str, res in ai_results.items():
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        if 0 <= idx < len(merged):
            confidence = _clamp_confidence(res.get("confidence", 0.0))
            # Do not write AI review fields when confidence is above 75%
            if confidence > AI_REVIEW_WRITE_MAX:
                continue
            status = str(res.get("status", "REVIEW")).upper()
            if status not in valid_statuses:
                status = "REVIEW"
            note = str(res.get("note", "")).strip()
            # Downgrade status to REVIEW if confidence is below threshold
            if status == "AGREE" and confidence < threshold:
                status = "REVIEW"
            merged[idx]["ai_confidence"] = confidence
            merged[idx]["ai_status"] = status
            merged[idx]["ai_note"] = note
            written += 1
    return written


def run_ai_review(merged, all_runs, batch_size=20, threshold=0.5, demo=False, sample_limit=0):
    """Run the optional Ollama AI review pass over split-vote courses."""
    borderline = collect_split_votes(merged, all_runs)
    if not borderline:
        print("\n[*] AI review: no split-vote courses found.")
        return

    if sample_limit and 0 < sample_limit < len(borderline):
        borderline = borderline[:sample_limit]
        print(f"\n[*] AI review: {len(borderline)} split-vote courses (sample limited).")
    else:
        print(f"\n[*] AI review: {len(borderline)} courses have split votes.")

    print(f"    Batch size: {batch_size} | confidence threshold: {threshold}")
    if demo:
        print("    Running in DEMO mode (no Ollama API calls).")

    ai_results = {}
    total_batches = (len(borderline) + batch_size - 1) // batch_size
    for i in range(0, len(borderline), batch_size):
        batch = borderline[i:i + batch_size]
        print(f"    Reviewing batch {i // batch_size + 1}/{total_batches} ({len(batch)} courses)...")
        res = call_ollama_review(batch, demo=demo)
        if res:
            ai_results.update(res)

    written = attach_ai_results(merged, ai_results, threshold=threshold)
    flagged = sum(1 for c in merged if c.get("ai_status") == "REVIEW")
    print(f"    AI reviewed {written} courses, flagged {flagged} for manual review.")
    if written < len(borderline):
        print(f"    [!] Note: {len(borderline) - written} high-confidence courses were not annotated.")


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
    parser.add_argument(
        "--ai-review", action="store_true",
        help="Run an Ollama AI review pass over split-vote courses and add ai_confidence/ai_status/ai_note fields."
    )
    parser.add_argument(
        "--ai-batch-size", type=int, default=10,
        help="Number of split-vote courses sent to Ollama in each batch (default: 10)."
    )
    parser.add_argument(
        "--ai-threshold", type=float, default=0.5,
        help="Confidence threshold below which a course is flagged for manual review (default: 0.5)."
    )
    parser.add_argument(
        "--ai-demo", action="store_true",
        help="Test the AI review code path without calling Ollama (returns placeholder REVIEW notes)."
    )
    parser.add_argument(
        "--sample-limit", type=int, default=0,
        help="Review only the first N borderline courses (0 = all). Useful for CI sanity checks."
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

    # 5b. Optional Ollama AI review pass for split-vote courses
    if args.ai_review or args.ai_demo:
        run_ai_review(
            merged, all_runs,
            batch_size=args.ai_batch_size,
            threshold=args.ai_threshold,
            demo=args.ai_demo,
            sample_limit=args.sample_limit
        )
        # Re-save JSON now that it contains AI review fields
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        print(f"[*] Updated {out_json} with AI review fields.")

    # 6. Generate PDF (same format as main workflow)
    print(f"\n[*] Generating PDF: {args.out}.pdf ...")
    try:
        agent = build_agent(merged, args.out)

        # Ensure every course with web_status is included in the PDF output
        for c in agent.courses:
            if not c.get("processed_this_run", False) and "web_status" in c:
                c["processed_this_run"] = True

        agent.generate_pdf_report(start_idx=0, end_idx=len(merged), pdf_name=args.out)
    except Exception as e:
        print(f"\n[!] PDF generation failed: {e}")
        print(f"    JSON output is still available at: {out_json}")
        # Do not claim success for the PDF.
        sys.exit(1)

    print(f"\n[✓] All done!")
    print(f"    JSON : {out_json}")
    print(f"    PDF  : {args.out}.pdf")


if __name__ == "__main__":
    main()
