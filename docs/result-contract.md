# 结构化研究结果接口

`scripts/workflow.py`接收UTF-8 JSON与Markdown。它校验结构、日期、价格、来源引用和候选门槛；不能证明所填来源的真实性，Codex研究员必须独立打开/采集来源并保留证据。本脚本不自动采集全市场数据，也不替代基本面研究。

顶层字段：

| 字段 | 类型/要求 |
| --- | --- |
| research_date | 北京时间YYYY-MM-DD |
| generated_at | 含时区ISO时间，转换北京日期后与研究日期一致 |
| run_mode | 默认scheduled；盘后手动验收可用manual_acceptance |
| baseline_date | 最近完整交易日YYYY-MM-DD；无法核验则null |
| status | complete / partial / insufficient / holiday |
| is_trade_day | true / false / null；未知用null |
| calendar_verified | 已打开核验交易所日历时才可true |
| strategy | 偏进攻、均衡、偏防守、观望或休市 |
| coverage | 实际范围与覆盖数量文字说明 |
| issues | 缺失/异常列表；partial及insufficient必须非空 |
| sources | 来源清单：id、kind、url、data_date、collected_at |
| candidates | 最多五只；holiday/insufficient必须空列表 |

正式scheduled运行的baseline_date必须早于研究日，不能用当日未收盘行情。manual_acceptance必须在北京时间15:30后，提供包含“盘后云端验收，非今日盘前计划”的manual_acceptance_note，归档报告和摘要必须保留该标签。同日基准还需baseline_close_verified=true、已核验交易日历及同日quote来源；这些标记不能代替实际来源核验。盘后验收存在候选时，plan_trade_date必须是研究日之后的已核验交易日，并标plan_trade_date_verified=true。任何模式均禁止未来基准日期。

来源kind包括calendar、quote、formal_report、forecast、analyst_estimate、announcement、news等。正式财报的data_date为报告期，公开日期及采集证据另存evidence。报价来源data_date必须为baseline_date。所有collected_at须有时区且不晚于generated_at。

每只候选通用字段：code（六位字符串）、name、board（上海主板/深圳主板）、board_verified、excluded_status（确认没有排除状态才false）、listing_date、priority（A/B/C）、quote_date、close、change_pct、source_ids、pattern、risk。上市不足三年的例外需listing_exception写出理由。

score_components可为null（未可靠评分），否则含value、quality、timing、risk_catalyst四项0至100分，并用score_evidence的同名字段写依据；综合分由脚本按30/30/25/15权重计算。主观评价的证据与各分项尺度须在报告说明。

A类附加必填字段：fundamentals_verified=true、major_risk=false、valuation_methods（至少两个不同name，各含assumptions、source_ids）、value_conservative、value_base、value_optimistic、buy_range（低/高）、stop、first_target_range（低/高）、atr14、volume_sample_count=20、average_turnover20、trigger、invalidation、price_basis、technical_evidence、valuation_uncertainty。

buy_range、stop、close和first_target_range使用人民币元，最多两位小数；支持数值或十进制字符串，禁止NaN/Infinity。要求stop < 买入下沿 <= 上沿 < 第一目标下沿，且以买入上沿和第一目标下沿计算风险收益比不低于2:1。B/C类buy_range必须为null或省略。

liquidity_threshold默认100000000元，如调整须提供liquidity_adjustment_reason。其他三年财务、最新市值、PE/PB/分位、MACD/RSI/均线/成交量、估值计算和来源完整性按tasks/research.md写入Markdown及证据文件，不能因为JSON只含校验字段而省略。

有效的数据不足结果示意（仅格式示意，不能当作已执行报告）：

```json
{
  "research_date": "2026-10-15",
  "generated_at": "2026-10-15T08:35:00+08:00",
  "baseline_date": null,
  "status": "insufficient",
  "is_trade_day": null,
  "calendar_verified": false,
  "strategy": "观望",
  "coverage": "未完成全市场筛选；公开数据接口不可用",
  "issues": ["交易日历和基准日行情无法验证"],
  "sources": [],
  "candidates": []
}
```
