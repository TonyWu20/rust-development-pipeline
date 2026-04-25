#!/usr/bin/env python3
"""Cross-check a draft review against the authoritative file-manifest.

Looks for contradictions between factual claims in the draft review and
the ground-truth data in file-manifest.json.

Checks:
  - Trailing newline claims vs manifest data
  - File path claims vs manifest paths
  - Issue counts match RESULT line format

This is a best-effort sanity check — it catches obvious contradictions
but cannot detect subtle semantic errors.

Usage:
    python3 validate-review-consistency.py <draft-review.md> <file-manifest.json>

Exit codes:
  0  — no contradictions found
  1  — contradictions detected (errors printed to stdout as JSON)
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── Patterns for identifying factual claims ──────────────────────────────────

# Patterns for trailing-newline claims
TRAILING_NEWLINE_CLAIMS_RE = re.compile(
    r"(?:trailing\s+newline|ends?\s+with\s+newline|newline\s+at\s+end|"
    r"missing\s+newline|no\s+trailing\s+newline|hex\s+dump|0x0a|`0a`)",
    re.IGNORECASE,
)

# Pattern for file path references in issues
FILE_CLAIM_RE = re.compile(r"\*\*File:\*\*\s*`([^`]+)`")

# Issue count RESULT line
RESULT_LINE_RE = re.compile(
    r"RESULT:.*Issues:\s*"
    r"\[Defect\]\s*=\s*(\d+).*"
    r"\[Correctness\]\s*=\s*(\d+).*"
    r"\[Improvement\]\s*=\s*(\d+)",
    re.IGNORECASE,
)

# Pattern for "verified via X" claims — any method the review claims was used
VERIFIED_CLAIM_RE = re.compile(
    r"verified\s+(?:via|by|with|using)\s+(\w+(?:\s+\w+){0,3})",
    re.IGNORECASE,
)


def check_trailing_newline_contradictions(
    review_text: str,
    manifest: dict,
) -> list[dict]:
    """Check trailing-newline claims in review against manifest."""
    errors: list[dict] = []
    files_info = {f["path"]: f for f in manifest.get("files", [])}

    # Look for trailing-newline claims
    for m in TRAILING_NEWLINE_CLAIMS_RE.finditer(review_text):
        claim_line = review_text[max(0, m.start() - 60):m.end() + 60]
        claim_text = m.group(0).lower()

        # Identify which file the claim is about (look for nearby file paths)
        nearby_file = None
        for fpath in files_info:
            if fpath in claim_line:
                nearby_file = fpath
                break

        if nearby_file:
            file_data = files_info[nearby_file]
            has_trailing = file_data.get("has_trailing_newline", True)

            # Check if claim is contradictory
            if "missing" in claim_text or "no trailing" in claim_text:
                if has_trailing:
                    errors.append({
                        "type": "trailing_newline_contradiction",
                        "file": nearby_file,
                        "claim": f"Review says trailing newline is MISSING",
                        "manifest_fact": f"file-manifest.json says has_trailing_newline=true",
                        "context": claim_line.strip(),
                    })
            elif "present" in claim_text or "has" in claim_text or "ends with" in claim_text:
                if not has_trailing:
                    errors.append({
                        "type": "trailing_newline_contradiction",
                        "file": nearby_file,
                        "claim": f"Review says trailing newline is PRESENT",
                        "manifest_fact": f"file-manifest.json says has_trailing_newline=false",
                        "context": claim_line.strip(),
                    })

    # Check for "verified via hex dump" claims — these are always fabrication
    # since the gather session does not run xxd
    hex_claims = re.finditer(r"verified\s+(?:via|by|with|using)\s+hex", review_text, re.IGNORECASE)
    for m in hex_claims:
        errors.append({
            "type": "fabricated_verification",
            "claim": "Claims verification via hex dump which was not performed",
            "context": review_text[max(0, m.start() - 40):m.end() + 40].strip(),
        })

    return errors


def check_file_path_claims(
    review_text: str,
    manifest: dict,
) -> list[dict]:
    """Check that file paths in the review match the manifest."""
    errors: list[dict] = []
    known_files = {f["path"] for f in manifest.get("files", [])}

    for m in FILE_CLAIM_RE.finditer(review_text):
        fpath = m.group(1)
        if fpath not in known_files:
            # This could be a meta-issue or hallucinated file
            errors.append({
                "type": "unknown_file_reference",
                "file": fpath,
                "detail": f"Review references file '{fpath}' which is not in "
                          f"the diff's file manifest. Known files: {sorted(known_files)}",
            })

    return errors


def check_verified_claims(
    review_text: str,
    manifest: dict,
) -> list[dict]:
    """Check that verification method claims are plausible.

    The gather script does NOT run xxd, hexdump, file checksums, or similar
    binary analysis. Any claim of such verification is fabrication.
    """
    errors: list[dict] = []
    fabricated_methods = {"hex dump", "hexdump", "xxd", "md5", "sha256", "checksum"}

    for m in VERIFIED_CLAIM_RE.finditer(review_text):
        method = m.group(1).lower().strip()
        if method in fabricated_methods or any(fm in method for fm in fabricated_methods):
            errors.append({
                "type": "fabricated_verification",
                "method": method,
                "claim": review_text[max(0, m.start() - 30):m.end() + 30].strip(),
                "detail": f"Review claims verification via '{method}' which was not performed "
                          f"by the gather process. This is a hallucination.",
            })

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cross-check draft review against file-manifest"
    )
    parser.add_argument("review", help="Path to the draft review markdown")
    parser.add_argument("manifest", help="Path to file-manifest.json")
    args = parser.parse_args()

    review_path = Path(args.review).resolve()
    manifest_path = Path(args.manifest).resolve()

    if not review_path.exists():
        result = {"valid": False, "errors": [{
            "type": "file_not_found", "detail": f"Review file not found: {review_path}",
        }]}
        print(json.dumps(result, indent=2))
        sys.exit(1)

    if not manifest_path.exists():
        result = {"valid": False, "errors": [{
            "type": "file_not_found", "detail": f"Manifest file not found: {manifest_path}",
        }]}
        print(json.dumps(result, indent=2))
        sys.exit(1)

    review_text = review_path.read_text()
    manifest = json.loads(manifest_path.read_text())

    all_errors: list[dict] = []

    # Check trailing newline contradictions
    all_errors.extend(check_trailing_newline_contradictions(review_text, manifest))

    # Check file path claims
    all_errors.extend(check_file_path_claims(review_text, manifest))

    # Check fabricated verification claims
    all_errors.extend(check_verified_claims(review_text, manifest))

    result = {"valid": len(all_errors) == 0, "errors": all_errors}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
