#!/usr/bin/env python3
"""Validate that every synthesized finding is traceable to inspected notes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from domain_lib import canonical_note_url, contains_ephemeral_token, require_list, require_object


def validate(source: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contains_ephemeral_token(result):
        errors.append("final evidence must not persist xsec_token")
    sources = require_list(result.get("sources"), "sources")
    source_ids = [item.get("note_id") for item in sources]
    if len(source_ids) != len(set(source_ids)):
        errors.append("source note IDs must be unique")
    allowed = set(source_ids)
    if "notes" in source:
        inspected = {note["note_id"]: note for note in source["notes"]}
        if not allowed <= set(inspected):
            errors.append("final sources must come from inspected notes")
        for item in sources:
            original = inspected.get(item.get("note_id"))
            if original and (
                item.get("url") != original.get("url")
                or item.get("title") != original.get("title")
                or item.get("author") != original.get("author")
                or item.get("search_backends") != original.get("search_backends")
                or item.get("detail_backend") != original.get("detail_backend")
                or item.get("evidence_level") != original.get("evidence_level")
            ):
                errors.append(f"final source changed inspected evidence: {item.get('note_id')}")
    for item in sources:
        if canonical_note_url(item.get("url"), item.get("note_id")) != item.get("url"):
            errors.append(f"source URL is not canonical: {item.get('note_id')}")
    finding_ids: set[str] = set()
    for finding in require_list(result.get("findings"), "findings"):
        finding_id = finding.get("finding_id")
        if finding_id in finding_ids:
            errors.append(f"duplicate finding ID: {finding_id}")
        finding_ids.add(finding_id)
        supporting = finding.get("supporting_note_ids", [])
        contradicting = finding.get("contradicting_note_ids", [])
        if not set(supporting) <= allowed or not set(contradicting) <= allowed:
            errors.append(f"finding references a note outside sources: {finding_id}")
        if set(supporting) & set(contradicting):
            errors.append(f"finding uses the same source as support and contradiction: {finding_id}")
        confidence = finding.get("confidence")
        if confidence == "high" and len(set(supporting)) < 3:
            errors.append(f"high confidence requires at least three sources: {finding_id}")
        if confidence == "high" and "notes" in source:
            authors = {
                note["author"]
                for note_id in set(supporting)
                for note in [
                    next(
                        (item for item in source["notes"] if item["note_id"] == note_id),
                        None,
                    )
                ]
                if note is not None
            }
            if len(authors) < 3:
                errors.append(
                    f"high confidence requires at least three independent authors: {finding_id}"
                )
        if confidence == "medium" and len(set(supporting)) < 2:
            errors.append(f"medium confidence requires at least two sources: {finding_id}")
    if result.get("status") == "complete" and not result.get("findings"):
        errors.append("complete result requires at least one finding")
    if len(result.get("manual_search_urls", [])) < 3:
        errors.append("at least three direct search URLs are required")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        result = require_object(json.loads(args.output.read_text(encoding="utf-8")), "output")
        errors = validate(source, result)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
