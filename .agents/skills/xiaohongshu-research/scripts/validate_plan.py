#!/usr/bin/env python3
"""Validate a bounded and diverse Xiaohongshu research plan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from domain_lib import normalized_text, require_list, require_object


def validate(source: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if plan.get("request_text") != source.get("request_text"):
        errors.append("plan.request_text must preserve the original request")
    collection = require_object(plan.get("collection"), "plan.collection")
    queries = require_list(collection.get("query_variants"), "query_variants")
    normalized = [normalized_text(query) for query in queries]
    if len(queries) < 3 or len(queries) > 5:
        errors.append("query_variants must contain three to five queries")
    if any(not query for query in normalized) or len(set(normalized)) != len(normalized):
        errors.append("query_variants must be non-empty and distinct after normalization")
    topic = require_object(plan.get("topic"), "plan.topic")
    concepts = [normalized_text(value) for value in require_list(topic.get("required_concepts"), "required_concepts")]
    if not concepts:
        errors.append("at least one required concept is needed")
    if not any(any(concept in query for concept in concepts) for query in normalized):
        errors.append("at least one query must contain a required concept")
    minimum = collection.get("minimum_rounds")
    maximum = collection.get("maximum_rounds")
    if not isinstance(minimum, int) or not isinstance(maximum, int) or not 3 <= minimum <= maximum <= 5:
        errors.append("round limits must satisfy 3 <= minimum <= maximum <= 5")
    if collection.get("candidate_limit", 0) < collection.get("detail_limit", 0):
        errors.append("candidate_limit must be at least detail_limit")
    pacing = require_object(collection.get("pacing"), "pacing")
    if pacing.get("maximum_parallel_pages") != 1:
        errors.append("maximum_parallel_pages must be one")
    interval = pacing.get("minimum_action_interval_seconds")
    if not isinstance(interval, (int, float)) or interval < 3:
        errors.append("minimum_action_interval_seconds must be at least 3")
    if pacing.get("risk_event_retries") != 0:
        errors.append("risk_event_retries must be zero")
    cache_seconds = pacing.get("reuse_observation_cache_seconds")
    if not isinstance(cache_seconds, int) or not 900 <= cache_seconds <= 3600:
        errors.append("reuse_observation_cache_seconds must be 900-3600")
    if collection.get("saturation", {}).get("consecutive_rounds") != 2:
        errors.append("saturation requires exactly two consecutive rounds")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        source = require_object(json.loads(args.input.read_text(encoding="utf-8")), "input")
        plan = require_object(json.loads(args.output.read_text(encoding="utf-8")), "output")
        errors = validate(source, plan)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
