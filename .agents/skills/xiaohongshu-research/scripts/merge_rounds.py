#!/usr/bin/env python3
"""Deduplicate Xiaohongshu rounds, calculate saturation, and select notes."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from domain_lib import (
    canonical_note_url,
    contains_ephemeral_token,
    normalized_text,
    parse_engagement,
    require_list,
    require_object,
)


def build_shortlist(payload: dict[str, Any]) -> dict[str, Any]:
    if contains_ephemeral_token(payload):
        raise ValueError("round evidence must not persist xsec_token")
    plan = require_object(payload.get("plan"), "plan")
    topic = require_object(plan.get("topic"), "plan.topic")
    collection = require_object(plan.get("collection"), "plan.collection")
    rounds = require_list(payload.get("rounds"), "rounds")
    candidates = require_list(payload.get("candidates"), "candidates")
    excluded = {normalized_text(value) for value in topic["excluded_concepts"] if normalized_text(value)}
    required = {normalized_text(value) for value in topic["required_concepts"] if normalized_text(value)}
    unique: dict[str, dict[str, Any]] = {}
    new_by_round: list[int] = []
    seen_before: set[str] = set()
    for round_data in rounds:
        round_id = round_data["round_id"]
        current_ids = {candidate["note_id"] for candidate in candidates if candidate["round_id"] == round_id}
        new_by_round.append(len(current_ids - seen_before))
        seen_before.update(current_ids)
        for candidate in candidates:
            if candidate["round_id"] != round_id:
                continue
            note_id = candidate["note_id"]
            existing = unique.get(note_id)
            if existing is None:
                url = canonical_note_url(candidate["url"], note_id)
                if url is None:
                    continue
                unique[note_id] = {
                    "candidate_id": candidate["candidate_id"],
                    "note_id": note_id,
                    "title": candidate["title"],
                    "author": candidate["author"],
                    "published_text": candidate["published_text"],
                    "likes_text": candidate["likes_text"],
                    "saves_text": candidate["saves_text"],
                    "comments_text": candidate["comments_text"],
                    "cover_url": candidate["cover_url"],
                    "url": url,
                    "source_backends": [candidate["source_backend"]],
                    "seen_in_rounds": [round_id],
                    "matched_queries": [candidate["query"]],
                    "rank_history": [candidate["result_rank"]],
                    "first_seen_at": candidate["retrieved_at"],
                    "last_seen_at": candidate["retrieved_at"],
                }
            else:
                if candidate["source_backend"] not in existing["source_backends"]:
                    existing["source_backends"].append(candidate["source_backend"])
                if round_id not in existing["seen_in_rounds"]:
                    existing["seen_in_rounds"].append(round_id)
                if candidate["query"] not in existing["matched_queries"]:
                    existing["matched_queries"].append(candidate["query"])
                existing["rank_history"].append(candidate["result_rank"])
                existing["last_seen_at"] = max(existing["last_seen_at"], candidate["retrieved_at"])
                for field in ("likes_text", "saves_text", "comments_text"):
                    if parse_engagement(candidate[field]) > parse_engagement(existing[field]):
                        existing[field] = candidate[field]
    selected: list[dict[str, Any]] = []
    removed = 0
    for note in unique.values():
        title = normalized_text(note["title"])
        if any(value in title for value in excluded):
            removed += 1
            continue
        if required and not any(value in title for value in required):
            removed += 1
            continue
        selected.append(note)

    def score(note: dict[str, Any]) -> tuple[int, int, Decimal, int, str]:
        engagement = (
            parse_engagement(note["likes_text"])
            + parse_engagement(note["saves_text"]) * Decimal("1.2")
            + parse_engagement(note["comments_text"]) * Decimal("1.5")
        )
        return (
            -len(note["matched_queries"]),
            -len(note["seen_in_rounds"]),
            -engagement,
            min(note["rank_history"]),
            note["note_id"],
        )

    selected.sort(key=score)
    shortlist = selected[: collection["detail_limit"]]
    if not shortlist:
        raise ValueError("no note remains after deterministic topic filtering")
    threshold = collection["saturation"]["min_new_unique_per_round"]
    saturated = (
        len(rounds) >= collection["minimum_rounds"]
        and len(new_by_round) >= 2
        and all(value <= threshold for value in new_by_round[-2:])
    )
    return {
        "plan": plan,
        "round_coverage": {
            "rounds_executed": len(rounds),
            "unique_notes": len(unique),
            "new_unique_by_round": new_by_round,
            "duplicate_observations": len(candidates) - len(unique),
            "source_backends": list(dict.fromkeys(round_data["source_backend"] for round_data in rounds)),
            "saturated": saturated,
            "stop_reason": payload["collection_status"]["stop_reason"],
            "blocked_reasons": payload["collection_status"]["blocked_reasons"],
        },
        "selection_summary": {
            "input_observations": len(candidates),
            "excluded_by_topic": removed,
            "selected_for_detail": len(shortlist),
        },
        "shortlist": shortlist,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        result = build_shortlist(payload)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
