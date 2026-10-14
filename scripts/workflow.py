"""Codex research artifacts and Feishu delivery. No scheduler or broker API."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")
HEADERS = ["研究日期", "股票代码", "股票名称", "前收盘价", "建议买入区间", "止损位",
           "目标价", "估计内在价值", "形态类型", "综合评分", "风险提示", "数据来源",
           "数据基准日", "版本标识"]
WEIGHTS = {"value": Decimal("0.30"), "quality": Decimal("0.30"),
           "timing": Decimal("0.25"), "risk_catalyst": Decimal("0.15")}
REPO = "https://github.com/i-meteor-shower/ashare-daily-research"


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field}: boolean is not a number")
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"{field}: invalid number") from None
    if not result.is_finite():
        raise ValueError(f"{field}: non-finite value")
    return result


def price(value, field):
    result = number(value, field)
    if result <= 0 or result != result.quantize(Decimal("0.01")):
        raise ValueError(f"{field}: price must be positive and on the 0.01 yuan tick")
    return result


def text_required(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: evidence text is required")
    return value


def validate(result):
    study = date.fromisoformat(result["research_date"])
    generated = datetime.fromisoformat(result["generated_at"])
    if generated.tzinfo is None or generated.astimezone(BEIJING).date() != study:
        raise ValueError("generated_at must be timezone-aware and match the Beijing research date")
    status = result["status"]
    if status not in {"complete", "partial", "insufficient", "holiday"}:
        raise ValueError("invalid research status")
    trade_day = result.get("is_trade_day")
    if trade_day is not None and type(trade_day) is not bool:
        raise ValueError("is_trade_day must be true, false or null")
    calendar_verified = result.get("calendar_verified") is True
    if status == "holiday" and (trade_day is not False or not calendar_verified):
        raise ValueError("holiday requires a verified non-trading day")
    if status in {"complete", "partial"} and (trade_day is not True or not calendar_verified):
        raise ValueError("research requires a verified trading day")
    base = result.get("baseline_date")
    if base and date.fromisoformat(base) >= study:
        raise ValueError("baseline must be a fully closed trading day before research date")
    if status in {"complete", "partial"} and not base:
        raise ValueError("baseline_date is required")
    if result["strategy"] not in {"偏进攻", "均衡", "偏防守", "观望", "休市"}:
        raise ValueError("invalid market strategy")
    if status == "holiday" and result["strategy"] != "休市":
        raise ValueError("holiday strategy must be 休市")
    text_required(result["coverage"], "coverage")
    if not isinstance(result.get("issues", []), list):
        raise ValueError("issues must be a list")
    if status in {"partial", "insufficient"} and not result.get("issues"):
        raise ValueError("data problems must be disclosed")
    sources = result.get("sources", [])
    source_ids = set()
    for source in sources:
        source_id = text_required(source["id"], "source.id")
        if source_id in source_ids:
            raise ValueError("duplicate source id")
        source_ids.add(source_id)
        parsed = urlparse(source["url"])
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise ValueError("source URL must be an attributable HTTP(S) URL")
        if "/bot/v2/hook/" in parsed.path:
            raise ValueError("a webhook is not a research source")
        if date.fromisoformat(source["data_date"]) > study:
            raise ValueError("future source data is forbidden")
        collected = datetime.fromisoformat(source["collected_at"])
        if collected.tzinfo is None or collected > generated:
            raise ValueError("source collection timestamp is invalid")
        text_required(source["kind"], "source.kind")
    if calendar_verified and not any(s.get("kind") == "calendar" for s in sources):
        raise ValueError("verified calendar requires a calendar source")
    candidates = result.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) > 5:
        raise ValueError("at most five candidates are allowed")
    if status in {"holiday", "insufficient"} and candidates:
        raise ValueError("holiday/insufficient runs cannot contain recommendations")
    seen = set()
    for stock in candidates:
        code = stock["code"]
        if not isinstance(code, str) or not re.fullmatch(r"(?:60[0135]|00[0123])\d{3}", code):
            raise ValueError("only verified Shanghai/Shenzhen main-board A-share codes are allowed")
        if code in seen:
            raise ValueError("duplicate candidate")
        seen.add(code)
        if stock.get("board_verified") is not True or stock.get("board") not in {"上海主板", "深圳主板"}:
            raise ValueError("main-board membership must be verified from a security list")
        name = text_required(stock["name"], "name")
        if "ST" in name.upper() or "退" in name or stock.get("excluded_status") is not False:
            raise ValueError("excluded security status")
        listed = date.fromisoformat(stock["listing_date"])
        anniversary = listed.replace(year=listed.year + 3, day=min(listed.day, 28)) if listed.month == 2 else listed.replace(year=listed.year + 3)
        if study < anniversary and not stock.get("listing_exception"):
            raise ValueError("listed less than three years")
        level = stock["priority"]
        if level not in {"A", "B", "C"}:
            raise ValueError("invalid candidate priority")
        if stock["quote_date"] != base:
            raise ValueError("candidate quote date is stale or inconsistent")
        price(stock["close"], "close")
        number(stock["change_pct"], "change_pct")
        refs = stock.get("source_ids", [])
        if not refs or any(s not in source_ids for s in refs):
            raise ValueError("candidate source references are missing")
        quote_sources = [s for s in sources if s["id"] in refs and s["kind"] == "quote"]
        if not any(s["data_date"] == base for s in quote_sources):
            raise ValueError("candidate requires a quote source for the baseline date")
        if stock.get("score_components") is not None:
            components = stock["score_components"]
            evidence = stock.get("score_evidence", {})
            for key in WEIGHTS:
                value = number(components[key], key)
                if not 0 <= value <= 100:
                    raise ValueError("component score outside 0..100")
                text_required(evidence.get(key), "score_evidence." + key)
        if level != "A":
            if stock.get("buy_range") is not None:
                raise ValueError("watchlist stocks must not have an executable buy range")
            continue
        if stock.get("fundamentals_verified") is not True or stock.get("major_risk") is not False:
            raise ValueError("A-class requires verified fundamentals and no known major deterioration")
        methods = stock.get("valuation_methods", [])
        if len({m.get("name") for m in methods}) < 2:
            raise ValueError("two distinct valuation methods are required")
        for method in methods:
            text_required(method.get("assumptions"), "valuation assumptions")
            if not method.get("source_ids") or any(s not in source_ids for s in method["source_ids"]):
                raise ValueError("valuation inputs require sources")
        conservative, intrinsic, optimistic = [number(stock[k], k) for k in ("value_conservative", "value_base", "value_optimistic")]
        if not 0 < conservative <= intrinsic <= optimistic:
            raise ValueError("invalid valuation scenarios")
        low, high = [price(p, "buy_range") for p in stock["buy_range"]]
        stop = price(stock["stop"], "stop")
        target_low, target_high = [price(p, "first_target_range") for p in stock["first_target_range"]]
        if not stop < low <= high < target_low <= target_high:
            raise ValueError("invalid long-position price ordering")
        if (target_low - high) / (high - stop) < 2:
            raise ValueError("risk/reward at the least favorable entry must be at least 2:1")
        if number(stock["atr14"], "ATR14") <= 0:
            raise ValueError("ATR14 must be calculated")
        if number(stock["volume_sample_count"], "volume_sample_count") != 20:
            raise ValueError("liquidity must use twenty trading days")
        threshold = number(result.get("liquidity_threshold", 100000000), "liquidity threshold")
        if threshold != 100000000:
            text_required(result.get("liquidity_adjustment_reason"), "liquidity adjustment reason")
        if threshold <= 0 or number(stock["average_turnover20"], "turnover20") < threshold:
            raise ValueError("insufficient liquidity")
        for field in ["trigger", "invalidation", "risk", "price_basis", "technical_evidence", "valuation_uncertainty"]:
            text_required(stock.get(field), field)
    return result


def score(stock):
    components = stock.get("score_components")
    if components is None:
        return "未可靠评分"
    total = sum(number(components[k], k) * w for k, w in WEIGHTS.items())
    return str(total.quantize(Decimal("0.1")))


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def lock(root):
    directory = root / ".local"
    directory.mkdir(exist_ok=True)
    path = directory / "archive.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("another archive is running or its lock requires review") from None
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def summary(result, report_relative):
    lines = [f"【A股每日研究】{result['research_date']}",
             f"行情基准日：{result.get('baseline_date') or '未验证'}",
             f"策略：{result['strategy']}｜数据状态：{result['status']}",
             "覆盖：" + result["coverage"]]
    if result["status"] == "holiday":
        lines.append("今日休市，不重复推送旧推荐。")
    elif result["status"] == "insufficient":
        lines.append("数据不足，无法验证是否存在合适买入候选。")
    else:
        buying = [s for s in result.get("candidates", []) if s["priority"] == "A"]
        if not buying:
            lines.append("今日无合适买入候选。")
        for stock in buying:
            low, high = stock["buy_range"]
            lines.extend([f"{stock['code']} {stock['name']}｜前收盘 {stock['close']}",
                          f"条件买入 {low}—{high}｜止损参考 {stock['stop']}｜第一目标 {stock['first_target_range']}",
                          "触发：" + stock["trigger"], "放弃：" + stock["invalidation"],
                          "风险：" + stock["risk"]])
        watching = [s for s in result.get("candidates", []) if s["priority"] != "A"]
        if watching:
            lines.append("观察池（无可执行买点）：" + "、".join(s["code"] + " " + s["name"] for s in watching))
    if result.get("issues"):
        lines.append("数据问题：" + "；".join(result["issues"]))
    lines.extend(["盘前条件计划，需盘中确认；止损不保证按参考价成交。",
                  "完整报告：" + REPO + "/blob/main/" + report_relative])
    return "\n".join(lines)


def archive(root, result, markdown):
    validate(result)
    if result["status"] != "holiday":
        for heading in ["市场概览", "候选股票排行榜", "单只股票深度分析", "今日操作优先级", "数据来源"]:
            if heading not in markdown:
                raise ValueError("report section missing: " + heading)
    if result["research_date"] not in markdown:
        raise ValueError("report must identify its research date")
    if "/bot/v2/hook/" in markdown or "/bot/v2/hook/" in json_text(result):
        raise ValueError("do not archive webhook credentials")
    version = hashlib.sha256((json_text(result) + markdown).encode("utf-8")).hexdigest()[:16]
    study = result["research_date"]
    run = root / "data" / "runs" / study / version
    with lock(root):
        run.mkdir(parents=True, exist_ok=True)
        canonical = root / "reports" / f"{study}.md"
        if (run / "manifest.json").exists():
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            report = root / manifest["report"]
        else:
            report = canonical if not canonical.exists() else root / "reports" / f"{study}.v{version}.md"
        if report.exists():
            if report.read_text(encoding="utf-8") != markdown:
                raise ValueError("an original report cannot be replaced")
        else:
            atomic_write(report, markdown)
        relative = report.relative_to(root).as_posix()
        atomic_write(run / "result.json", json_text(result))
        manifest = {"version": version, "research_date": study, "baseline_date": result.get("baseline_date"),
                    "report": relative, "result": (run / "result.json").relative_to(root).as_posix()}
        atomic_write(run / "manifest.json", json_text(manifest))
        atomic_write(run / "summary.txt", summary(result, relative))
        history_path = root / "data" / "recommendation_history.csv"
        rows = []
        if history_path.exists():
            with history_path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != HEADERS:
                    raise ValueError("history columns changed; explicit migration required")
                rows = list(reader)
        seen = {(r["研究日期"], r["股票代码"], r["版本标识"]) for r in rows}
        for stock in result.get("candidates", []):
            key = (study, stock["code"], version)
            if key in seen:
                continue
            buying = stock["priority"] == "A"
            values = [study, stock["code"], stock["name"], stock["close"],
                      "—".join(map(str, stock["buy_range"])) if buying else "",
                      stock["stop"] if buying else "",
                      "—".join(map(str, stock["first_target_range"])) if buying else "",
                      stock.get("value_base", ""), stock.get("pattern", "待确认"), score(stock),
                      stock.get("risk", "待核验"), "|".join(s["url"] for s in result["sources"] if s["id"] in stock["source_ids"]),
                      result.get("baseline_date", ""), version]
            rows.append(dict(zip(HEADERS, values)))
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        atomic_write(history_path, buffer.getvalue())
        receipt = run / "delivery.json"
        if not receipt.exists():
            atomic_write(receipt, json_text({"state": "prepared", "attempts": 0, "version": version}))
    return run


def endpoint_from_env():
    endpoint = os.environ.get("FEISHU_WEBHOOK_URL", "")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.hostname != "open.feishu.cn" or parsed.port not in (None, 443) or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("FEISHU_WEBHOOK_URL must be an authorized Feishu HTTPS endpoint")
    if not re.fullmatch(r"/open-apis/bot/v2/hook/[0-9a-fA-F-]{36}", parsed.path):
        raise ValueError("invalid Feishu webhook path")
    return endpoint


def post(endpoint, body):
    request = Request(endpoint, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        codes = [data[k] for k in ("code", "StatusCode") if k in data]
        if not codes or any(type(c) is not int for c in codes):
            return "unknown", "unrecognized response status"
        if all(c == 0 for c in codes):
            return "sent", "success"
        return "failed", "Feishu business code " + "/".join(map(str, codes))
    except HTTPError as error:
        if 400 <= error.code < 500:
            return "failed", "HTTP " + str(error.code)
        return "unknown", "HTTP " + str(error.code) + "; delivery not confirmed"
    except (URLError, TimeoutError, OSError, ValueError, TypeError, UnicodeError):
        # Never log the exception URL, credentials, or raw response body.
        return "unknown", "connection or response interrupted; delivery not confirmed"


def persist_receipt(root, path):
    relative = path.relative_to(root).as_posix()
    for command in (["git", "add", "--", relative],
                    ["git", "commit", "-m", "Record Feishu delivery state", "--", relative],
                    ["git", "push", "origin", "HEAD:main"]):
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True)
        if completed.returncode != 0:
            raise ValueError("delivery state could not be persisted to GitHub; no automatic resend")


def deliver(root, run, persist=True, transport=post, sleep=time.sleep):
    run = run.resolve()
    if not run.is_relative_to((root / "data" / "runs").resolve()):
        raise ValueError("run must be an archived research run")
    path = run / "delivery.json"
    with lock(root):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if receipt["state"] != "prepared":
            return receipt  # pending/unknown/failed/sent all require explicit review or are final.
        endpoint = endpoint_from_env()
        content = (run / "summary.txt").read_text(encoding="utf-8")
        body = json.dumps({"msg_type": "text", "content": {"text": content}}, ensure_ascii=False).encode("utf-8")
        if len(body) > 18000:
            raise ValueError("summary exceeds safe message size; shorten it without dropping conditions")
        receipt.update(state="pending", started_at=datetime.now(BEIJING).isoformat())
        atomic_write(path, json_text(receipt))
        if persist:
            persist_receipt(root, path)  # Must succeed before the external side effect.
        for attempt in range(1, 4):
            state, detail = transport(endpoint, body)
            receipt.update(state=state, detail=detail, attempts=attempt,
                           checked_at=datetime.now(BEIJING).isoformat())
            atomic_write(path, json_text(receipt))
            if state != "failed" or attempt == 3:
                break
            sleep(attempt)
        if persist:
            persist_receipt(root, path)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate")
    check.add_argument("result", type=Path)
    save = commands.add_parser("archive")
    save.add_argument("result", type=Path)
    save.add_argument("report", type=Path)
    send = commands.add_parser("send")
    send.add_argument("run", type=Path)
    send.add_argument("--local-test", action="store_true", help="Skip remote receipt persistence only for an explicit local smoke test")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command in {"validate", "archive"}:
            result = json.loads(args.result.read_text(encoding="utf-8"))
            validate(result)
            if args.command == "archive":
                run = archive(root, result, args.report.read_text(encoding="utf-8"))
                print(json_text({"run": str(run), "status": "archived"}))
            else:
                print(json_text({"status": "valid", "research_date": result["research_date"]}))
        else:
            receipt = deliver(root, args.run, persist=not args.local_test)
            print(json_text(receipt))
            return 0 if receipt["state"] == "sent" else 2
    except (ValueError, KeyError, TypeError) as error:
        print(json_text({"status": "invalid_or_blocked", "reason": str(error)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
