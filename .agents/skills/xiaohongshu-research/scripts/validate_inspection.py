#!/usr/bin/env python3
"""Validate Xiaohongshu note evidence against the selected sources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from domain_lib import canonical_note_url, require_list, require_object, time_is_fresh


def validate(shortlist: dict[str, Any], inspection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if inspection.get("plan") != shortlist.get("plan"):
        errors.append("inspection must preserve the complete plan")
    if inspection.get("round_coverage") != shortlist.get("round_coverage"):
        errors.append("inspection must preserve round coverage")
    expected = {note["note_id"]: note for note in require_list(shortlist.get("shortlist"), "shortlist")}
    notes = require_list(inspection.get("notes"), "notes")
    seen: set[str] = set()
    verified = 0
    comments_read = 0
    for note in notes:
        note_id = note.get("note_id")
        if note_id in seen:
            errors.append(f"duplicate inspected note: {note_id}")
        seen.add(note_id)
        source = expected.get(note_id)
        if source is None:
            errors.append(f"inspection contains note outside shortlist: {note_id}")
            continue
        if canonical_note_url(note.get("url"), note_id) != source["url"]:
            errors.append(f"inspection URL does not match shortlist: {note_id}")
        if note.get("seen_in_rounds") != source["seen_in_rounds"] or note.get("rank_history") != source["rank_history"]:
            errors.append(f"inspection changed round evidence: {note_id}")
        if not time_is_fresh(note.get("retrieved_at")):
            errors.append(f"inspection time is missing, invalid, or stale: {note_id}")
        claim_ids = [claim.get("claim_id") for claim in note.get("claims", [])]
        if len(claim_ids) != len(set(claim_ids)):
            errors.append(f"claim IDs must be unique within note: {note_id}")
        for comment in note.get("comments", []):
            comments_read += 1
            unknown = set(comment.get("related_claim_ids", [])) - set(claim_ids)
            if unknown:
                errors.append(f"comment references unknown claim IDs in note {note_id}")
        if note.get("evidence_level") == "A":
            verified += 1
            if not note.get("claims") or not note.get("content_summary"):
                errors.append(f"A-level note requires content and claims: {note_id}")
    coverage = require_object(inspection.get("inspection_coverage"), "inspection_coverage")
    if coverage.get("notes_attempted") != len(notes) + len(coverage.get("failed_urls", [])):
        errors.append("notes_attempted must equal notes plus failed URLs")
    if coverage.get("notes_verified") != verified:
        errors.append("notes_verified must equal A-level notes")
    if coverage.get("comments_read") != comments_read:
        errors.append("comments_read must equal the stored public comments")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        shortlist = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        inspection = require_object(json.loads(args.output.read_text(encoding="utf-8")), "output")
        errors = validate(shortlist, inspection)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
