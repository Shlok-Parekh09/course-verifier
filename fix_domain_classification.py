"""
fix_domain_classification.py
============================
Re-classifies course domains in frontend/1.json by intelligently
detecting the correct course type from the course name keywords.

Priority order (highest to lowest):
  1. Post Graduate Certificate keywords -> "Post Graduate Certificate"
  2. Post Graduate Diploma keywords     -> "Post Graduate Diploma"
  3. PhD / Doctorate                    -> "PhD"
  4. Master's / M.Tech / M.Sc / MBA    -> "Master's Degree"
  5. Bachelor's / B.Tech / B.E. / BCA  -> "Bachelor's Degree"
  6. Diploma                            -> "Diploma"
  7. Certificate                        -> "Certificate"
  8. Anything unidentifiable            -> leave unchanged

KEY DISTINCTION:
  Post Graduate CERTIFICATE = shorter credential, not a full degree:
    e.g. "PG Certificate in Cybersecurity", "Graduate Certificate"
  Post Graduate DIPLOMA = longer, structured program (usually 1 year):
    e.g. "PG Diploma in Cybersecurity", "PGDM in Information Security"
"""

import json
from collections import Counter

INPUT_JSON = "frontend/1.json"

# ── Keyword tables (all lowercase, checked in order) ────────────────

# Must check PG Cert BEFORE general "certificate" and PG Diploma BEFORE "diploma"

PG_CERT_KW = [
    "post graduate certificate",
    "postgraduate certificate",
    "post-graduate certificate",
    "post graduation certificate",
    "pg certificate",
    "pg cert",
    "p.g. certificate",
    "p.g.c.",
    "graduate certificate",     # e.g. "Cybersecurity Graduate Certificate"
    "pg certification",         # e.g. "PG Certification in Cyber Security"
    "post graduate certification",
    "postgraduate certification",
]

PG_DIPLOMA_KW = [
    "post graduate diploma",
    "postgraduate diploma",
    "post-graduate diploma",
    "pg diploma",
    "p.g. diploma",
    "p.g.d.",
    "pgdm",                     # Post Graduate Diploma in Management
    "pgdca",                    # PG Diploma in Computer Applications
    "graduate diploma",
    "advanced diploma",         # often equivalent to PG diploma
]

PHD_KW = [
    "ph.d",
    "phd",
    "doctor of philosophy",
    "doctorate",
    "d.phil",
]

MASTERS_KW = [
    # Explicit Masters
    "master of ",
    "master's degree",
    "master's in",
    "masters in ",
    "masters degree",
    "master in ",
    # Abbreviations
    "m.s. ",
    "m.s in",
    "m.s.",
    " ms in ",
    "ms cyber",
    "ms data",
    "ms network",
    "ms information",
    "m.tech",
    "m. tech",
    " mtech ",
    "m.sc.",
    "m.sc ",
    " msc ",
    "m.e. ",
    "m.e in",
    " me in ",
    "m.c.a",
    " mca ",
    "m.b.a",
    " mba ",
    "m.phil",
    "m.arch",
    "m.plan",
    "(m.sc)",
    "(m.tech)",
    # Specific patterns from the PDF
    "cybersecurity (m.sc.)",
    "cybersecurity m.sc",
]

BACHELORS_KW = [
    # Explicit Bachelor's
    "bachelor of ",
    "bachelor's degree",
    "bachelor's in",
    "bachelor in ",
    # B.Tech / B.E.
    "b.tech",
    "b. tech",
    " btech",
    "b.e.",
    "b.e ",
    "be cse",
    "be b.e",
    "b.e-",
    # B.Sc
    "b.sc",
    "b. sc",
    "b.sc.",
    # BCA / BBA / B.Com
    "b.c.a",
    " bca ",
    "bca-",
    " bba ",
    "b.com",
    # B.Arch / B.Plan / B.Des
    "b.arch",
    "b.plan",
    "b.des",
    # BS
    "b.s. in",
    " bs in ",
    "b.s in",
    # Undergraduate
    "undergraduate",
]

DIPLOMA_KW = [
    # Must NOT trigger on PG Diploma (already handled above)
    "diploma in ",
    "diploma on ",
    " diploma ",
    " diploma-",
]

CERT_KW = [
    # Must NOT trigger on PG Certificate (already handled above)
    "certificate course",
    "certificate program",
    "certificate in ",
    "certification in ",
    " certification",
    "certification course",
]


def _implied_type(n: str):
    """Return implied course type key from name string (lowercased)."""
    # 1. Post Graduate Certificate (must come before general "certificate")
    for kw in PG_CERT_KW:
        if kw in n:
            return "pgcert"
    # 2. Post Graduate Diploma (must come before general "diploma")
    for kw in PG_DIPLOMA_KW:
        if kw in n:
            return "pgdip"
    # 3. PhD
    for kw in PHD_KW:
        if kw in n:
            return "phd"
    # 4. Master's
    for kw in MASTERS_KW:
        if kw in n:
            return "master"
    # 5. Bachelor's
    for kw in BACHELORS_KW:
        if kw in n:
            return "bachelor"
    # 6. Diploma (general, non-PG)
    for kw in DIPLOMA_KW:
        if kw in n:
            return "diploma"
    # 7. Certificate (general, non-PG)
    for kw in CERT_KW:
        if kw in n:
            return "cert"
    return None


def _current_matches(domain: str, implied: str) -> bool:
    """Check if the stored domain already matches the implied type."""
    d = domain.lower()
    checks = {
        "pgcert":   lambda d: "post graduate certificate" in d or "pg certificate" in d or "graduate certificate" in d,
        "pgdip":    lambda d: "post graduate diploma" in d or "pg diploma" in d,
        "phd":      lambda d: "phd" in d or "ph.d" in d or "doctorate" in d,
        "master":   lambda d: "master" in d,
        "bachelor": lambda d: "bachelor" in d,
        "diploma":  lambda d: "diploma" in d and "post" not in d,
        "cert":     lambda d: "certificate" in d and "post" not in d and "graduate" not in d,
    }
    return checks.get(implied, lambda d: False)(d)


CANONICAL = {
    "pgcert":   "Post Graduate Certificate",
    "pgdip":    "Post Graduate Diploma",
    "phd":      "PhD",
    "master":   "Master's Degree",
    "bachelor": "Bachelor's Degree",
    "diploma":  "Diploma",
    "cert":     "Certificate",
}


def classify(name: str, current_domain: str):
    """
    Return corrected domain string if wrong, else None (leave as-is).
    """
    n = name.lower().strip()
    implied = _implied_type(n)
    if implied is None:
        return None  # Can't determine from name; leave unchanged

    if _current_matches(current_domain or "", implied):
        return None  # Already correct

    return CANONICAL[implied]


# ── Raw-value canonical map ──────────────────────────────────────────
# Verbatim strings that come directly from PDF extraction and need
# to be normalized to proper display strings.
RAW_CANONICAL = {
    "bachelors degree":             "Bachelor's Degree",
    "bachelor degree":              "Bachelor's Degree",
    "bachelor's degree":            "Bachelor's Degree",
    "masters degree":               "Master's Degree",
    "master degree":                "Master's Degree",
    "master's degree":              "Master's Degree",
    "post graduate diploma":        "Post Graduate Diploma",
    "post graduate certificate":    "Post Graduate Certificate",
    "postgraduate diploma":         "Post Graduate Diploma",
    "postgraduate certificate":     "Post Graduate Certificate",
    "pg diploma":                   "Post Graduate Diploma",
    "pg certificate":               "Post Graduate Certificate",
    "diploma":                      "Diploma",
    "certificate":                  "Certificate",
    "free to audit":                "Free to Audit",
    "free":                         "Free",
    "high value low cost":          "High Value Low Cost",
    "phd":                          "PhD",
    "ph.d":                         "PhD",
}


def canonicalize_raw(domain: str):
    """
    If the raw domain is an all-caps or inconsistently-cased known value,
    return the canonical display string. Returns None if already correct.
    """
    if not domain:
        return None
    normalised = domain.lower().strip()
    canonical = RAW_CANONICAL.get(normalised)
    if canonical and canonical != domain:
        return canonical
    return None


def main():
    print(f"[*] Loading {INPUT_JSON}...")
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"    {len(data)} courses loaded.")

    print(f"\n[*] Before fix - Domain distribution:")
    before_counts = Counter(c.get("domain", "") for c in data)
    for domain, count in sorted(before_counts.items(), key=lambda x: -x[1]):
        print(f"    {count:>6}: {domain}")

    fixed = 0
    changes_log = []

    for c in data:
        name = str(c.get("name", ""))
        current = str(c.get("domain", ""))

        # ── Pass 1: canonicalize raw all-caps / mis-cased values ──
        canonical = canonicalize_raw(current)
        if canonical:
            changes_log.append({"id": c.get("id"), "name": name,
                                 "old": current, "new": canonical})
            c["domain"] = canonical
            current = canonical
            fixed += 1

        # ── Pass 2: keyword-based reclassification ─────────────────
        corrected = classify(name, current)
        if corrected and corrected != current:
            changes_log.append({"id": c.get("id"), "name": name,
                                 "old": current, "new": corrected})
            c["domain"] = corrected
            fixed += 1

    print(f"\n[*] Fixed {fixed} entries (normalization + reclassification).")

    if changes_log:
        print(f"\n    Sample of changes (first 30):")
        for entry in changes_log[:30]:
            print(f"      id={entry.get('id','?'):>5}: {entry['name'][:52]:<52} | {entry['old']:>25} -> {entry['new']}")
        if len(changes_log) > 30:
            print(f"      ... and {len(changes_log)-30} more.")

    print(f"\n[*] After fix - Domain distribution:")
    after_counts = Counter(c.get("domain", "") for c in data)
    for domain, count in sorted(after_counts.items(), key=lambda x: -x[1]):
        print(f"    {count:>6}: {domain}")

    print(f"\n[*] Saving {INPUT_JSON}...")
    with open(INPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] Done. {INPUT_JSON} updated with {fixed} total corrections.")


if __name__ == "__main__":
    main()

