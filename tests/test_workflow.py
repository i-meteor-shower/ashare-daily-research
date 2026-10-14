"""All market values here are synthetic fixtures, never recommendations."""
import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import workflow as w

WORKSPACE = Path(__file__).resolve().parents[1]
TEST_TEMP_ROOT = (WORKSPACE / ".local" / "test-temp").resolve()
if not TEST_TEMP_ROOT.is_relative_to(WORKSPACE):
    raise RuntimeError("test temporary files must stay inside the workspace")
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def sample():
    return {
        "research_date": "2026-10-15", "generated_at": "2026-10-15T08:45:00+08:00",
        "baseline_date": "2026-10-14", "status": "complete", "is_trade_day": True,
        "calendar_verified": True, "strategy": "均衡", "coverage": "虚构测试样本，未采集真实市场数据",
        "issues": [], "sources": [
            {"id": "calendar", "kind": "calendar", "url": "https://example.invalid/calendar",
             "data_date": "2026-10-15", "collected_at": "2026-10-15T08:31:00+08:00"},
            {"id": "quote", "kind": "quote", "url": "https://example.invalid/quote",
             "data_date": "2026-10-14", "collected_at": "2026-10-15T08:31:00+08:00"},
            {"id": "financial", "kind": "formal_report", "url": "https://example.invalid/financial",
             "data_date": "2026-06-30", "collected_at": "2026-10-15T08:32:00+08:00"}],
        "candidates": [{
            "code": "600000", "name": "虚构测试样本", "board": "上海主板", "board_verified": True,
            "excluded_status": False, "listing_date": "2000-01-01", "priority": "A",
            "quote_date": "2026-10-14", "close": "10.00", "change_pct": "1.00",
            "source_ids": ["quote", "financial"], "fundamentals_verified": True, "major_risk": False,
            "valuation_methods": [
                {"name": "PE", "assumptions": "虚构测试假设", "source_ids": ["financial"]},
                {"name": "PB_ROE", "assumptions": "虚构测试假设", "source_ids": ["financial"]}],
            "value_conservative": "13", "value_base": "15", "value_optimistic": "17",
            "buy_range": ["10.10", "10.50"], "stop": "10.00", "first_target_range": ["12.00", "13.00"],
            "atr14": "0.50", "volume_sample_count": 20, "average_turnover20": 200000000,
            "trigger": "仅供自动化测试的条件", "invalidation": "仅供测试的失效条件",
            "risk": "虚构样本，不可交易", "price_basis": "虚构ATR及支撑测试数据",
            "technical_evidence": "虚构测试结构", "valuation_uncertainty": "全部数据为测试值",
            "pattern": "A缩量回踩", "score_components": None}]
    }


def report(study="2026-10-15"):
    return f"# {study} 虚构测试报告\n\n" + "\n".join(
        "## " + h for h in ["市场概览", "今日候选股票排行榜", "单只股票深度分析", "今日操作优先级", "数据来源"])


class ValidationTests(unittest.TestCase):
    def test_accept_structurally_complete_candidate(self):
        w.validate(sample())

    def test_reject_stale_quote_and_current_day_baseline(self):
        for modify in (lambda r: r.update(baseline_date=r["research_date"]),
                       lambda r: r["candidates"][0].update(quote_date="2026-10-13")):
            result = sample()
            modify(result)
            with self.assertRaises(ValueError):
                w.validate(result)

    def test_reject_unsupported_security_and_st(self):
        for change in ({"code": "300001"}, {"code": "688001"}, {"name": "*ST测试"}, {"board_verified": False}):
            result = sample()
            result["candidates"][0].update(change)
            with self.assertRaises(ValueError):
                w.validate(result)

    def test_reject_bad_risk_reward_and_price_precision(self):
        for change in ({"first_target_range": ["11.00", "12.00"]}, {"stop": "10.501"}, {"atr14": "NaN"}):
            result = sample()
            result["candidates"][0].update(change)
            with self.assertRaises(ValueError):
                w.validate(result)

    def test_reject_valuation_and_evidence_gaps(self):
        for change in ({"valuation_methods": []}, {"source_ids": []}, {"trigger": ""}, {"major_risk": True}):
            result = sample()
            result["candidates"][0].update(change)
            with self.assertRaises(ValueError):
                w.validate(result)

    def test_holiday_and_insufficient_do_not_recommend(self):
        result = sample()
        result.update(status="holiday", is_trade_day=False, strategy="休市", candidates=[])
        w.validate(result)
        result["calendar_verified"] = False
        with self.assertRaises(ValueError):
            w.validate(result)
        result.update(status="insufficient", is_trade_day=None, strategy="观望", baseline_date=None,
                      issues=["无法验证交易日历"])
        w.validate(result)
        result["candidates"] = sample()["candidates"]
        with self.assertRaises(ValueError):
            w.validate(result)

    def test_watchlist_has_no_buy_plan(self):
        result = sample()
        result["candidates"][0].update(priority="B", buy_range=None)
        w.validate(result)
        text = w.summary(result, "reports/2026-10-15.md")
        self.assertNotIn("条件买入", text)
        self.assertIn("观察池", text)

    def test_score_requires_all_evidence(self):
        result = sample()
        stock = result["candidates"][0]
        stock["score_components"] = dict.fromkeys(w.WEIGHTS, 80)
        with self.assertRaises(ValueError):
            w.validate(result)
        stock["score_evidence"] = dict.fromkeys(w.WEIGHTS, "虚构测试依据")
        w.validate(result)
        self.assertEqual(w.score(stock), "80.0")


class ArchiveTests(unittest.TestCase):
    def test_same_version_is_idempotent_and_new_version_keeps_original(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            original = report()
            first = w.archive(root, sample(), original)
            self.assertEqual(first, w.archive(root, sample(), original))
            second = w.archive(root, sample(), original + "\n不同版本\n")
            self.assertNotEqual(first, second)
            self.assertEqual((root / "reports/2026-10-15.md").read_text(encoding="utf-8"), original)
            with (root / "data/recommendation_history.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertNotEqual(rows[0]["版本标识"], rows[1]["版本标识"])

    def test_missing_data_produces_no_history_rows(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT) as directory:
            root = Path(directory)
            result = sample()
            result.update(status="insufficient", calendar_verified=False, is_trade_day=None,
                          baseline_date=None, candidates=[], issues=["测试：行情缺失"])
            run = w.archive(root, result, report())
            self.assertIn("数据不足", (run / "summary.txt").read_text(encoding="utf-8"))
            with (root / "data/recommendation_history.csv").open(encoding="utf-8", newline="") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [])


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=TEST_TEMP_ROOT)
        self.root = Path(self.directory.name)
        self.run = w.archive(self.root, sample(), report())
        self.environment = patch.dict(os.environ, {"FEISHU_WEBHOOK_URL":
            "https://open.feishu.cn/open-apis/bot/v2/hook/00000000-0000-0000-0000-000000000000"})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def test_success_not_resent(self):
        calls = []
        def transport(*args):
            calls.append(args)
            return "sent", "success"
        self.assertEqual(w.deliver(self.root, self.run, False, transport)["state"], "sent")
        w.deliver(self.root, self.run, False, transport)
        self.assertEqual(len(calls), 1)

    def test_unknown_not_retried(self):
        calls = []
        def transport(*args):
            calls.append(args)
            return "unknown", "timeout"
        receipt = w.deliver(self.root, self.run, False, transport)
        self.assertEqual(receipt["state"], "unknown")
        w.deliver(self.root, self.run, False, transport)
        self.assertEqual(len(calls), 1)

    def test_definite_failures_have_bounded_retries(self):
        calls = []
        def transport(*args):
            calls.append(args)
            return "failed", "test rejection"
        receipt = w.deliver(self.root, self.run, False, transport, lambda _: None)
        self.assertEqual(receipt["attempts"], 3)
        self.assertEqual(len(calls), 3)

    def test_remote_persistence_failure_prevents_send(self):
        calls = []
        with patch.object(w, "persist_receipt", side_effect=ValueError("test push failed")):
            with self.assertRaises(ValueError):
                w.deliver(self.root, self.run, True, lambda *args: calls.append(args))
        self.assertEqual(calls, [])
        saved = json.loads((self.run / "delivery.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["state"], "pending")

    def test_reject_wrong_webhook_destination(self):
        with patch.dict(os.environ, {"FEISHU_WEBHOOK_URL": "https://example.invalid/webhook"}):
            with self.assertRaises(ValueError):
                w.deliver(self.root, self.run, False)


if __name__ == "__main__":
    unittest.main()
