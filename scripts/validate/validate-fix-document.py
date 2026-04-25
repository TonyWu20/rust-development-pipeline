#!/usr/bin/env python3
"""Validate a fix document (markdown) against format rules and the diff manifest.

Checks:
  - Every issue uses ``### Issue N:`` format (colon, not em dash)
  - Classification is exactly ``Defect`` or ``Correctness``
  - Severity is exactly ``Blocking``, ``Major``, or ``Minor``
  - Every ``**File:**`` path exists in file-manifest.json (catches meta-issues)
  - Every issue has all required fields present
  - Sequential numbering starting from 1

Usage:
    python3 validate-fix-document.py <fix-document.md> [--manifest file-manifest.json]

Exit codes:
  0  — validation passed
  1  — validation failed (errors printed to stdout as JSON)
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── Patterns ─────────────────────────────────────────────────────────────────

# Issue header: "### Issue N: <title>"
ISSUE_HEADER_RE = re.compile(r"^###\s+Issue\s+(\d+):\s*(.*)", re.MULTILINE)

# Field patterns
CLASSIFICATION_RE = re.compile(r"\*\*Classification:\*\*\s*(\S+)")
FILE_RE = re.compile(r"\*\*File:\*\*\s*`([^`]+)`")
SEVERITY_RE = re.compile(r"\*\*Severity:\*\*\s*(\S+)")
PROBLEM_RE = re.compile(r"\*\*Problem:\*\*")
FIX_RE = re.compile(r"\*\*Fix:\*\*")

VALID_CLASSIFICATIONS = {"Defect", "Correctness"}
VALID_SEVERITIES = {"Blocking", "Major", "Minor"}


# ── Parsing ──────────────────────────────────────────────────────────────────


def parse_sections(text: str) -> list[dict]:
    """Split the document into per-issue sections and parse each."""
    issues: list[dict] = []
    matches = list(ISSUE_HEADER_RE.finditer(text))

    if not matches:
        # Check if it's "No fixes required"
        if "No fixes required" in text:
            return []
        return [{"raw": text, "error": "No issue headers found"}]

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end]

        issue = {
            "number": int(m.group(1)),
            "title": m.group(2).strip(),
            "raw": section_text,
        }

        # Extract fields
        class_m = CLASSIFICATION_RE.search(section_text)
        issue["classification"] = class_m.group(1) if class_m else None

        file_m = FILE_RE.search(section_text)
        issue["file"] = file_m.group(1) if file_m else None

        sev_m = SEVERITY_RE.search(section_text)
        issue["severity"] = sev_m.group(1) if sev_m else None

        issue["has_problem"] = PROBLEM_RE.search(section_text) is not None
        issue["has_fix"] = FIX_RE.search(section_text) is not None

        issues.append(issue)

    return issues


def validate_issue(issue: dict, known_files: set[str]) -> list[dict]:
    """Validate a single issue section.  Returns list of errors."""
    errors: list[dict] = []

    # Check sequential numbering
    # (We check this externally since we need the full list)

    # Classification
    cls = issue.get("classification")
    if cls is None:
        errors.append({
            "type": "missing_classification",
            "issue": issue["number"],
            "detail": f"Issue {issue['number']}: missing or unparseable "
                      f"'**Classification:**' field",
        })
    elif cls not in VALID_CLASSIFICATIONS:
        errors.append({
            "type": "invalid_classification",
            "issue": issue["number"],
            "value": cls,
            "detail": f"Issue {issue['number']}: classification '{cls}' is not "
                      f"valid. Must be one of: {', '.join(sorted(VALID_CLASSIFICATIONS))}",
        })

    # Severity
    sev = issue.get("severity")
    if sev is None:
        errors.append({
            "type": "missing_severity",
            "issue": issue["number"],
            "detail": f"Issue {issue['number']}: missing or unparseable "
                      f"'**Severity:**' field",
        })
    elif sev not in VALID_SEVERITIES:
        errors.append({
            "type": "invalid_severity",
            "issue": issue["number"],
            "value": sev,
            "detail": f"Issue {issue['number']}: severity '{sev}' is not "
                      f"valid. Must be one of: {', '.join(sorted(VALID_SEVERITIES))}",
        })

    # File path check
    file_path = issue.get("file")
    if file_path is None:
        errors.append({
            "type": "missing_file",
            "issue": issue["number"],
            "detail": f"Issue {issue['number']}: missing '**File:**' field",
        })
    elif known_files and file_path not in known_files:
        errors.append({
            "type": "file_not_in_diff",
            "issue": issue["number"],
            "file": file_path,
            "detail": f"Issue {issue['number']}: file '{file_path}' is not in "
                      f"the diff's changed files. This may be a meta-issue about "
                      f"the review process rather than the PR code. "
                      f"Known files: {sorted(known_files)}",
        })

    # Problem section
    if not issue.get("has_problem"):
        errors.append({
            "type": "missing_problem",
            "issue": issue["number"],
            "detail": f"Issue {issue['number']}: missing '**Problem:**' section",
        })

    # Fix section
    if not issue.get("has_fix"):
        errors.append({
            "type": "missing_fix",
            "issue": issue["number"],
            "detail": f"Issue {issue['number']}: missing '**Fix:**' section",
        })

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a fix document against format rules"
    )
    parser.add_argument("document", help="Path to the fix document (markdown)")
    parser.add_argument(
        "--manifest", help="Path to file-manifest.json for file path validation"
    )
    args = parser.parse_args()

    doc_path = Path(args.document).resolve()
    if not doc_path.exists():
        result = {
            "valid": False,
            "errors": [{
                "type": "file_not_found",
                "detail": f"Fix document not found: {doc_path}",
            }],
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    text = doc_path.read_text()

    # Special case: "No fixes required"
    if "No fixes required" in text:
        result = {"valid": True, "errors": []}
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # Load manifest if given
    known_files: set[str] = set()
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    if manifest_path and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            known_files = {f["path"] for f in manifest.get("files", [])}
        except (json.JSONDecodeError, OSError) as e:
            result = {"valid": False, "errors": [{"type": "manifest_read_error", "detail": str(e)}]}
            print(json.dumps(result, indent=2))
            sys.exit(1)

    issues = parse_sections(text)

    if not issues:
        result = {"valid": False, "errors": [{"type": "no_issues", "detail": "No issue sections found in fix document"}]}
        print(json.dumps(result, indent=2))
        sys.exit(1)

    all_errors: list[dict] = []

    # Check sequential numbering
    for i, issue in enumerate(issues):
        expected = i + 1
        if issue.get("number") and issue["number"] != expected:
            all_errors.append({
                "type": "non_sequential_numbering",
                "issue": issue.get("number"),
                "expected": expected,
                "detail": f"Issue is numbered {issue['number']} but expected {expected} "
                          f"(1-based sequential numbering required)",
            })

    # Check format consistency (colon after number, not em dash)
    for i, m in enumerate(ISSUE_HEADER_RE.finditer(text)):
        header_text = m.group(0)
        if "—" in header_text or "–" in header_text or ":" not in header_text:
            all_errors.append({
                "type": "invalid_header_format",
                "issue": int(m.group(1)),
                "detail": f"Issue header uses wrong delimiter. Must be "
                          f"'### Issue N:' with colon, not em dash or other delimiter. "
                          f"Found: '{header_text}'",
            })

    # Validate each issue
    for issue in issues:
        all_errors.extend(validate_issue(issue, known_files))

    result = {"valid": len(all_errors) == 0, "errors": all_errors}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
