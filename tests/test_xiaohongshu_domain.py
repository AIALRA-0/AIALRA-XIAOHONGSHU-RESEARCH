from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "xiaohongshu-research"
sys.path.insert(0, str(SKILL / "scripts"))

from domain_lib import (  # noqa: E402
    canonical_note_url,
    contains_ephemeral_token,
    note_id_from_url,
    official_search_url,
)
from learn import ensure_learning_record_is_safe  # noqa: E402
from merge_rounds import build_shortlist  # noqa: E402
from validate_final import validate as validate_final  # noqa: E402
from validate_inspection import validate as validate_inspection  # noqa: E402
from validate_plan import validate as validate_plan  # noqa: E402
from validate_round_results import validate as validate_round_results  # noqa: E402


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat()


def sample_source() -> dict:
    return {
        "request_text": "研究 2026 年东京自由行值得去的展览和注意事项",
        "topic_type": "travel",
        "region": "东京",
        "time_focus": "2026 年",
        "detail_limit": 6,
        "comments_per_note": 10,
    }


def sample_plan() -> dict:
    return {
        "request_text": sample_source()["request_text"],
        "research_question": "2026 年东京自由行有哪些值得去的展览与实际注意事项",
        "topic": {
            "canonical_topic": "2026 东京自由行展览攻略",
            "topic_type": "travel",
            "required_concepts": ["东京", "展览"],
            "excluded_concepts": ["大阪"],
        },
        "scope": {"region": "东京", "time_focus": "2026 年"},
        "evaluation_dimensions": ["展期", "票价", "预约", "交通", "排队风险"],
        "collection": {
            "query_variants": [
                "东京 展览 2026 攻略",
                "东京 自由行 展览 预约",
                "东京 展览 避坑 排队",
            ],
            "sort_modes": ["comprehensive", "latest"],
            "minimum_rounds": 3,
            "maximum_rounds": 5,
            "candidate_limit": 80,
            "detail_limit": 6,
            "comments_per_note": 10,
            "saturation": {
                "min_new_unique_per_round": 1,
                "consecutive_rounds": 2,
            },
            "pacing": {
                "maximum_parallel_pages": 1,
                "minimum_action_interval_seconds": 3,
                "risk_event_retries": 0,
                "reuse_observation_cache_seconds": 900,
            },
        },
        "assumptions": ["只研究公开笔记"],
    }


def candidate(
    candidate_id: str,
    note_id: str,
    round_id: str,
    query: str,
    title: str,
    rank: int,
    *,
    sort_mode: str = "comprehensive",
    likes: str = "100",
) -> dict:
    return {
        "candidate_id": candidate_id,
        "note_id": note_id,
        "round_id": round_id,
        "query": query,
        "sort_mode": sort_mode,
        "source_backend": "aialra-shopping-browser",
        "result_rank": rank,
        "title": title,
        "author": f"作者{candidate_id}",
        "published_text": "2026-01-10",
        "likes_text": likes,
        "saves_text": "50",
        "comments_text": "10",
        "cover_url": "https://img.invalid/cover.jpg",
        "url": f"https://www.xiaohongshu.com/explore/{note_id}",
        "retrieved_at": now_iso(),
    }


def sample_round_results() -> dict:
    plan = sample_plan()
    queries = plan["collection"]["query_variants"]
    note_a = "67abcde0123456789abcde01"
    note_b = "67abcde0123456789abcde02"
    note_c = "67abcde0123456789abcde03"
    note_bad = "67abcde0123456789abcde04"
    rounds = [
        {"round_id": "round-1", "query": queries[0], "sort_mode": "comprehensive", "source_backend": "aialra-shopping-browser", "retrieved_at": now_iso(), "result_count": 3},
        {"round_id": "round-2", "query": queries[1], "sort_mode": "comprehensive", "source_backend": "aialra-shopping-browser", "retrieved_at": now_iso(), "result_count": 2},
        {"round_id": "round-3", "query": queries[2], "sort_mode": "latest", "source_backend": "aialra-shopping-browser", "retrieved_at": now_iso(), "result_count": 2},
    ]
    cards = [
        candidate("c1", note_a, "round-1", queries[0], "2026 东京展览完整攻略", 1, likes="1.2万"),
        candidate("c2", note_b, "round-1", queries[0], "东京展览预约和票价", 2, likes="5000"),
        candidate("c3", note_bad, "round-1", queries[0], "大阪展览攻略", 3),
        candidate("c4", note_a, "round-2", queries[1], "2026 东京展览完整攻略", 2),
        candidate("c5", note_c, "round-2", queries[1], "东京展览排队避坑", 1),
        candidate("c6", note_a, "round-3", queries[2], "2026 东京展览完整攻略", 3, sort_mode="latest"),
        candidate("c7", note_c, "round-3", queries[2], "东京展览排队避坑", 2, sort_mode="latest"),
    ]
    return {
        "plan": plan,
        "collection_status": {"stop_reason": "saturated", "blocked_reasons": []},
        "rounds": rounds,
        "candidates": cards,
    }


def inspected_note(source: dict, claim_id: str, statement: str) -> dict:
    return {
        "note_id": source["note_id"],
        "title": source["title"],
        "author": source["author"],
        "url": source["url"],
        "published_at": source["published_text"],
        "content_summary": statement,
        "image_urls": [source["cover_url"]],
        "search_backends": source["source_backends"],
        "detail_backend": "aialra-shopping-browser",
        "metrics": {
            "likes": source["likes_text"],
            "saves": source["saves_text"],
            "comments": source["comments_text"],
        },
        "claims": [
            {
                "claim_id": claim_id,
                "statement": statement,
                "claim_type": "fact",
                "evidence": "正文直接列出展期与预约要求",
            }
        ],
        "comments": [
            {
                "text": "现场确实需要提前预约",
                "relation": "supports",
                "related_claim_ids": [claim_id],
            }
        ],
        "commercial_signals": [],
        "caveats": [],
        "evidence_level": "A",
        "retrieved_at": now_iso(),
        "seen_in_rounds": source["seen_in_rounds"],
        "rank_history": source["rank_history"],
    }


class XiaohongshuDomainTests(unittest.TestCase):
    def test_ephemeral_detail_link_is_read_only_input_and_never_stored(self) -> None:
        note_id = "67abcde0123456789abcde01"
        transient = (
            f"https://www.xiaohongshu.com/search_result/{note_id}"
            "?xsec_token=temporary-value&xsec_source=pc_search"
        )
        self.assertEqual(note_id, note_id_from_url(transient))
        self.assertEqual(
            f"https://www.xiaohongshu.com/explore/{note_id}",
            canonical_note_url(transient, note_id),
        )
        self.assertTrue(contains_ephemeral_token(transient))
        payload = sample_round_results()
        payload["candidates"][0]["url"] = transient
        errors = validate_round_results(payload["plan"], payload)
        self.assertTrue(any("xsec_token" in error for error in errors))
        with self.assertRaisesRegex(ValueError, "xsec_token"):
            build_shortlist(payload)

    def test_ephemeral_token_is_rejected_from_nested_evidence(self) -> None:
        shortlist = build_shortlist(sample_round_results())
        note = inspected_note(
            shortlist["shortlist"][0],
            "reservation-required",
            "热门展览需要提前预约",
        )
        inspection = {
            "plan": shortlist["plan"],
            "round_coverage": shortlist["round_coverage"],
            "inspection_coverage": {
                "notes_attempted": 1,
                "notes_verified": 1,
                "comments_read": 1,
                "failed_urls": [],
            },
            "notes": [note],
        }
        inspection["notes"][0]["comments"][0]["text"] = (
            "xsec_token=temporary-value"
        )
        errors = validate_inspection(shortlist, inspection)
        self.assertTrue(any("xsec_token" in error for error in errors))
        with self.assertRaisesRegex(ValueError, "xsec_token"):
            ensure_learning_record_is_safe(
                "记录 xsec_token=temporary-value",
                "review:detail-check",
            )

    def test_plan_requires_diverse_bounded_rounds(self) -> None:
        self.assertEqual([], validate_plan(sample_source(), sample_plan()))
        duplicate = sample_plan()
        duplicate["collection"]["query_variants"][1] = duplicate["collection"]["query_variants"][0]
        self.assertTrue(validate_plan(sample_source(), duplicate))

    def test_round_merge_keeps_stability_and_filters_wrong_topic(self) -> None:
        payload = sample_round_results()
        self.assertEqual([], validate_round_results(payload["plan"], payload))
        result = build_shortlist(payload)
        self.assertEqual([3, 1, 0], result["round_coverage"]["new_unique_by_round"])
        self.assertTrue(result["round_coverage"]["saturated"])
        self.assertEqual(3, result["round_coverage"]["duplicate_observations"])
        note_ids = {item["note_id"] for item in result["shortlist"]}
        self.assertNotIn("67abcde0123456789abcde04", note_ids)
        first = next(item for item in result["shortlist"] if item["note_id"] == "67abcde0123456789abcde01")
        self.assertEqual(["round-1", "round-2", "round-3"], first["seen_in_rounds"])
        self.assertEqual(["aialra-shopping-browser"], first["source_backends"])
        self.assertEqual(["aialra-shopping-browser"], result["round_coverage"]["source_backends"])

    def test_mixed_backend_provenance_is_preserved(self) -> None:
        payload = sample_round_results()
        payload["rounds"][1]["source_backend"] = "opencli"
        for item in payload["candidates"]:
            if item["round_id"] == "round-2":
                item["source_backend"] = "opencli"
        self.assertEqual([], validate_round_results(payload["plan"], payload))
        result = build_shortlist(payload)
        repeated = next(
            item
            for item in result["shortlist"]
            if item["note_id"] == "67abcde0123456789abcde01"
        )
        self.assertEqual(["aialra-shopping-browser", "opencli"], repeated["source_backends"])
        self.assertEqual(
            ["aialra-shopping-browser", "opencli"],
            result["round_coverage"]["source_backends"],
        )

    def test_inspection_and_final_require_traceable_source_ids(self) -> None:
        shortlist = build_shortlist(sample_round_results())
        notes = [
            inspected_note(shortlist["shortlist"][0], "reservation-required", "热门展览需要提前预约"),
            inspected_note(shortlist["shortlist"][1], "reservation-required", "热门展览需要提前预约"),
        ]
        inspection = {
            "plan": shortlist["plan"],
            "round_coverage": shortlist["round_coverage"],
            "inspection_coverage": {
                "notes_attempted": 2,
                "notes_verified": 2,
                "comments_read": 2,
                "failed_urls": [],
            },
            "notes": notes,
        }
        self.assertEqual([], validate_inspection(shortlist, inspection))
        sources = [
            {
                "note_id": note["note_id"],
                "title": note["title"],
                "author": note["author"],
                "url": note["url"],
                "published_at": note["published_at"],
                "search_backends": note["search_backends"],
                "detail_backend": note["detail_backend"],
                "evidence_level": note["evidence_level"],
                "commercial_signals": note["commercial_signals"],
                "retrieved_at": note["retrieved_at"],
            }
            for note in notes
        ]
        final = {
            "status": "complete",
            "research_snapshot": {
                "question": inspection["plan"]["research_question"],
                "topic": inspection["plan"]["topic"]["canonical_topic"],
                "region": "东京",
                "time_focus": "2026 年",
                "retrieved_at": now_iso(),
            },
            "summary": "两篇独立笔记都提示热门展览需要提前预约",
            "findings": [
                {
                    "finding_id": "finding-1",
                    "statement": "热门展览需要提前预约",
                    "confidence": "medium",
                    "supporting_note_ids": [note["note_id"] for note in notes],
                    "contradicting_note_ids": [],
                    "caveats": ["展览规则会变化"],
                }
            ],
            "sources": sources,
            "round_coverage": inspection["round_coverage"],
            "inspection_coverage": inspection["inspection_coverage"],
            "manual_search_urls": [official_search_url(query) for query in inspection["plan"]["collection"]["query_variants"]],
            "warnings": [],
        }
        self.assertEqual([], validate_final(inspection, final))
        self.assertEqual(["aialra-shopping-browser"], final["sources"][0]["search_backends"])
        self.assertEqual("aialra-shopping-browser", final["sources"][0]["detail_backend"])
        final["findings"][0]["confidence"] = "high"
        self.assertTrue(validate_final(inspection, final))
        final["findings"][0]["confidence"] = "medium"
        final["findings"][0]["supporting_note_ids"].append("unknown-note-id")
        self.assertTrue(validate_final(inspection, final))

    def test_skill_is_general_read_only_and_explicit_about_captcha(self) -> None:
        workflow = json.loads((SKILL / "workflow.yaml").read_text(encoding="utf-8"))
        effects = {node["side_effect"] for node in workflow["execution"]["graph"]["nodes"]}
        self.assertLessEqual(effects, {"none", "read"})
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("旅游、购物、餐饮、住宿、教程、趋势", text)
        self.assertIn("至少三轮", text)
        self.assertIn("验证码", text)
        self.assertIn("不使用隐身浏览器", text)

    def test_backend_routing_prefers_only_allowlisted_read_operations(self) -> None:
        workflow = json.loads((SKILL / "workflow.yaml").read_text(encoding="utf-8"))
        nodes = {node["id"]: node for node in workflow["execution"]["graph"]["nodes"]}
        search_routing = nodes["collect-search-rounds"]["action"]["arguments"]["source_routing"]
        detail_routing = nodes["inspect-notes"]["action"]["arguments"]["source_routing"]
        self.assertEqual(
            ["aialra-shopping-browser", "opencli"],
            search_routing["provider_order"],
        )
        self.assertEqual(
            ["xiaohongshu.search"],
            search_routing["providers"]["opencli"]["allowed_operations"],
        )
        self.assertEqual(
            ["xiaohongshu.note", "xiaohongshu.comments"],
            detail_routing["providers"]["opencli"]["allowed_operations"],
        )
        for routing in (search_routing, detail_routing):
            self.assertEqual(
                {"provider_order", "providers", "selection_policy"},
                set(routing),
            )
            self.assertIn(
                "account-write",
                routing["providers"]["opencli"]["prohibited_operation_classes"],
            )
            self.assertIn(
                "credential-read",
                routing["providers"]["opencli"]["prohibited_operation_classes"],
            )
            self.assertEqual(
                "aialra-shopping-browser",
                routing["providers"]["aialra-shopping-browser"]["identifier"],
            )
            self.assertIn(
                "policy-blocked",
                routing["selection_policy"]["hard_stop_kinds"],
            )
        for node_id in ("collect-search-rounds", "inspect-notes"):
            node = nodes[node_id]
            arguments = node["action"]["arguments"]
            self.assertEqual(1, arguments["maximum_parallel_pages"])
            self.assertGreaterEqual(arguments["minimum_action_interval_seconds"], 3)
            self.assertEqual(0, arguments["risk_event_retries"])
            self.assertGreaterEqual(arguments["reuse_observation_cache_seconds"], 900)
            self.assertEqual(0, node["max_retries"])
        routing_text = (SKILL / "references" / "backend-routing.md").read_text(encoding="utf-8")
        self.assertIn("没有明确许可证的项目只能学习公开思路", routing_text)
        self.assertIn("本仓库不自动安装 OpenCLI", routing_text)


class XiaohongshuRunnerEndToEndTests(unittest.TestCase):
    def run_runner(self, *arguments: str) -> dict:
        completed = subprocess.run(
            [
                sys.executable,
                str(SKILL / "scripts" / "runner.py"),
                *arguments,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        return json.loads(completed.stdout)

    def write_json(self, directory: Path, name: str, value: dict) -> Path:
        path = directory / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_runner_completes_full_graph_with_traceable_finding(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            started = self.run_runner(
                "start",
                "--input",
                str(self.write_json(directory, "input.json", sample_source())),
            )
            state_id = started["state_id"]
            directive = self.run_runner("advance", "--state-id", state_id)
            self.assertEqual("plan-research", directive["node"]["id"])
            directive = self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "plan-research",
                "--output",
                str(self.write_json(directory, "plan.json", sample_plan())),
            )
            self.assertEqual("collect-search-rounds", directive["node"]["id"])
            directive = self.run_runner("advance", "--state-id", state_id)
            self.assertEqual("collect-search-rounds", directive["node"]["id"])
            directive = self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "collect-search-rounds",
                "--output",
                str(self.write_json(directory, "rounds.json", sample_round_results())),
            )
            self.assertEqual("merge-and-select", directive["node"]["id"])
            directive = self.run_runner("advance", "--state-id", state_id)
            self.assertEqual("inspect-notes", directive["node"]["id"])
            shortlist = build_shortlist(sample_round_results())
            notes = [
                inspected_note(shortlist["shortlist"][0], "reservation-required", "热门展览需要提前预约"),
                inspected_note(shortlist["shortlist"][1], "reservation-required", "热门展览需要提前预约"),
            ]
            inspection = {
                "plan": shortlist["plan"],
                "round_coverage": shortlist["round_coverage"],
                "inspection_coverage": {
                    "notes_attempted": 2,
                    "notes_verified": 2,
                    "comments_read": 2,
                    "failed_urls": [],
                },
                "notes": notes,
            }
            directive = self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "inspect-notes",
                "--output",
                str(self.write_json(directory, "inspection.json", inspection)),
            )
            self.assertEqual("synthesize-findings", directive["node"]["id"])
            directive = self.run_runner("advance", "--state-id", state_id)
            self.assertEqual("synthesize-findings", directive["node"]["id"])
            sources = [
                {
                    "note_id": note["note_id"],
                    "title": note["title"],
                    "author": note["author"],
                    "url": note["url"],
                    "published_at": note["published_at"],
                    "search_backends": note["search_backends"],
                    "detail_backend": note["detail_backend"],
                    "evidence_level": note["evidence_level"],
                    "commercial_signals": note["commercial_signals"],
                    "retrieved_at": note["retrieved_at"],
                }
                for note in notes
            ]
            final = {
                "status": "complete",
                "research_snapshot": {
                    "question": inspection["plan"]["research_question"],
                    "topic": inspection["plan"]["topic"]["canonical_topic"],
                    "region": inspection["plan"]["scope"]["region"],
                    "time_focus": inspection["plan"]["scope"]["time_focus"],
                    "retrieved_at": now_iso(),
                },
                "summary": "两个独立来源都提示热门展览需要提前预约",
                "findings": [
                    {
                        "finding_id": "finding-1",
                        "statement": "热门展览需要提前预约",
                        "confidence": "medium",
                        "supporting_note_ids": [note["note_id"] for note in notes],
                        "contradicting_note_ids": [],
                        "caveats": ["具体规则需要临行前复核"],
                    }
                ],
                "sources": sources,
                "round_coverage": inspection["round_coverage"],
                "inspection_coverage": inspection["inspection_coverage"],
                "manual_search_urls": [
                    official_search_url(query)
                    for query in inspection["plan"]["collection"]["query_variants"]
                ],
                "warnings": [],
            }
            completed = self.run_runner(
                "submit",
                "--state-id",
                state_id,
                "--node-id",
                "synthesize-findings",
                "--output",
                str(self.write_json(directory, "final.json", final)),
            )
            self.assertEqual("completed", completed["status"])
            self.assertEqual(
                notes[0]["note_id"],
                completed["final_output"]["findings"][0]["supporting_note_ids"][0],
            )


if __name__ == "__main__":
    unittest.main()
