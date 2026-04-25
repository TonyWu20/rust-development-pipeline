#!/usr/bin/env python3
"""Validate a TOML fix/implementation plan against the compilable-plan-spec.

Checks:
  - Valid TOML syntax
  - Every ``[tasks.X]`` has a valid ``type`` in {replace, create, delete}
  - ``replace`` tasks have both ``before`` and ``after``
  - ``create`` tasks have ``after`` but no ``before``
  - ``delete`` tasks have ``before`` but no ``after``
  - Task IDs match the pattern ``TASK-N``, ``Issue-N``, ``Fix-N``, ``FIX-N``
  - Every ``[[tasks.X.changes]]`` has a ``file`` field
  - File paths exist in the supplied file-manifest.json (--manifest)
  - Acceptance commands are present

Usage:
    python3 validate-toml-plan.py <plan.toml> [--manifest file-manifest.json]

Exit codes:
  0  — validation passed
  1  — validation failed (errors printed to stdout as JSON)
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


VALID_TYPES = {"replace", "create", "delete"}
VALID_ID_RE = re.compile(r"^(TASK|Issue|Fix|FIX)-\d+$", re.IGNORECASE)


def validate(
    plan_path: Path,
    manifest_path: Path | None,
) -> list[dict]:
    """Validate a TOML plan file.  Returns a list of error dicts (empty = valid)."""
    errors: list[dict] = []

    # Load manifest if given
    known_files: set[str] = set()
    if manifest_path and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            known_files = {f["path"] for f in manifest.get("files", [])}
        except (json.JSONDecodeError, OSError) as e:
            errors.append({"type": "manifest_read_error", "detail": str(e)})

    # Parse TOML
    try:
        data = tomllib.loads(plan_path.read_text())
    except Exception as e:
        errors.append({"type": "parse_error", "detail": str(e)})
        return errors

    tasks_section = data.get("tasks", {})
    if not tasks_section:
        errors.append({"type": "no_tasks", "detail": "No [tasks] section found"})
        return errors

    for task_id, task_data in tasks_section.items():
        # Validate task ID format
        if not VALID_ID_RE.match(str(task_id)):
            errors.append({
                "type": "invalid_task_id",
                "task": task_id,
                "detail": f"Task ID '{task_id}' does not match pattern "
                          f"TASK-N, Issue-N, Fix-N, or FIX-N",
            })

        # Validate type
        explicit_type = task_data.get("type")
        if explicit_type is None:
            # Inferred from changes; check changes exist
            changes = task_data.get("changes", [])
            if not changes:
                errors.append({
                    "type": "no_type_no_changes",
                    "task": task_id,
                    "detail": f"Task '{task_id}' has no 'type' and no 'changes'",
                })
            continue

        task_type = str(explicit_type).lower()
        if task_type not in VALID_TYPES:
            errors.append({
                "type": "invalid_type",
                "task": task_id,
                "value": task_type,
                "valid_types": sorted(VALID_TYPES),
                "detail": f"Task '{task_id}' has invalid type '{task_type}'. "
                          f"Valid types: {', '.join(sorted(VALID_TYPES))}",
            })
            continue  # skip further validation for this task

        # Validate changes
        changes = task_data.get("changes", [])
        if not changes:
            errors.append({
                "type": "no_changes",
                "task": task_id,
                "detail": f"Task '{task_id}' has no [[changes]] entries",
            })

        for ci, change in enumerate(changes):
            # Check file field
            file_path = change.get("file")
            if not file_path:
                errors.append({
                    "type": "missing_file",
                    "task": task_id,
                    "change_index": ci,
                    "detail": f"Task '{task_id}', change #{ci}: missing 'file' field",
                })
                continue

            # Check file exists in manifest
            if known_files and file_path not in known_files:
                errors.append({
                    "type": "file_not_in_diff",
                    "task": task_id,
                    "file": file_path,
                    "detail": f"Task '{task_id}': file '{file_path}' is not in the "
                              f"diff's changed files. Known files: {sorted(known_files)}",
                })

            has_before = change.get("before") is not None
            has_after = change.get("after") is not None

            # Type-specific checks
            if task_type == "replace" and not (has_before and has_after):
                errors.append({
                    "type": "replace_missing_fields",
                    "task": task_id,
                    "change_index": ci,
                    "detail": f"Task '{task_id}', change #{ci}: type=replace "
                              f"requires both 'before' and 'after'",
                })
            elif task_type == "create" and not has_after:
                errors.append({
                    "type": "create_missing_after",
                    "task": task_id,
                    "change_index": ci,
                    "detail": f"Task '{task_id}', change #{ci}: type=create "
                              f"requires 'after'",
                })
            elif task_type == "create" and has_before:
                errors.append({
                    "type": "create_has_before",
                    "task": task_id,
                    "change_index": ci,
                    "detail": f"Task '{task_id}', change #{ci}: type=create "
                              f"should not have 'before'",
                })
            elif task_type == "delete" and not has_before:
                errors.append({
                    "type": "delete_missing_before",
                    "task": task_id,
                    "change_index": ci,
                    "detail": f"Task '{task_id}', change #{ci}: type=delete "
                              f"requires 'before'",
                })
            elif task_type == "delete" and has_after:
                errors.append({
                    "type": "delete_has_after",
                    "task": task_id,
                    "change_index": ci,
                    "detail": f"Task '{task_id}', change #{ci}: type=delete "
                              f"should not have 'after'",
                })

        # Validate acceptance commands
        acceptance = task_data.get("acceptance", [])
        if not acceptance:
            errors.append({
                "type": "missing_acceptance",
                "task": task_id,
                "detail": f"Task '{task_id}' has no 'acceptance' commands",
            })

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a TOML plan against the compilable plan spec"
    )
    parser.add_argument("plan", help="Path to the TOML plan file")
    parser.add_argument(
        "--manifest", help="Path to file-manifest.json for path validation"
    )
    args = parser.parse_args()

    plan_path = Path(args.plan).resolve()
    if not plan_path.exists():
        result = {
            "valid": False,
            "errors": [{
                "type": "file_not_found",
                "detail": f"Plan file not found: {plan_path}",
            }],
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    manifest_path = Path(args.manifest).resolve() if args.manifest else None

    errors = validate(plan_path, manifest_path)
    result = {"valid": len(errors) == 0, "errors": errors}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
