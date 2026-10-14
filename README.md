# A股每日低估值选股与交易计划

Codex原生云端研究任务配置与报告归档/飞书摘要工具。每天Asia/Shanghai 08:30开始，公开数据优先，每次独立研究；先经营质量和估值，后技术入场条件。不进行真实交易。

**当前状态：配置已准备，尚未启用云端定时任务。** `config/cloud-task.json`不是已注册日程，不能仅凭该文件声称已创建。正式启用需要可用的原生云端调度入口、发布环境和完整云端试运行。

## 运行内容

- `tasks/research.md`：完整十部分研究规则，包含范围、估值、技术形态、风险控制、报告和历史。
- `tasks/cloud-run.md`：提交给Codex原生云端任务的固定执行指令。
- `scripts/workflow.py`：结构化结果校验、版本报告、历史CSV、操作摘要和飞书回执。
- `docs/result-contract.md`：研究结果输入接口。脚本不代替联网数据采集与公司研究。

仓库由用户创建于 `i-meteor-shower/ashare-daily-research`。用户最新确认保持公开；真实Webhook不得提交。报告和历史记录也按仓库存储设置保存。

## 云端配置

1. 在Codex Cloud中建立专用环境，选择此仓库并准备Python 3.11或更高版本；工具只用Python标准库。
2. 环境允许获取已核验的公开行情、财报、交易所日历及公告，并允许访问`open.feishu.cn`。
3. 将授权群机器人地址配置到秘密变量`FEISHU_WEBHOOK_URL`。默认GitHub认证应有本仓库main读写权限，禁止在文件中存令牌。
4. 配置提交身份；手动验证读取最新历史、联网更新、完成研究、保存和推送。
5. 使用Codex的原生云端定时任务入口，名称为“A股每日低估值选股与交易计划”，每天北京时间08:30、独立运行、账号默认模型，指令采用tasks/cloud-run.md。
6. 核对任务实际运行位置、时区和下一次执行时间，写入真实环境/任务标识后更新状态。若入口不可用，保留prepared_not_scheduled，不建立本地或第三方替代日程。

官方说明：[云端环境](https://learn.chatgpt.com/docs/environments/cloud-environments)、[定时任务](https://learn.chatgpt.com/docs/automations)。云端环境与定时日程是不同配置，发布环境不等于已经注册日程。

## 校验与归档

```sh
python -m unittest discover -s tests -v
python scripts/workflow.py validate result.json
python scripts/workflow.py archive result.json report.md
```

archive输出run目录。将报告、证据、原始结果和历史先推送仓库，随后：

```sh
python scripts/workflow.py send data/runs/YYYY-MM-DD/VERSION
```

send会先持久保存pending回执再发请求，发后保存最终回执。它只暂存/提交当前delivery.json，不提交其他未完成工作；push冲突停止，禁止强制覆盖。测试时可显式使用`--local-test`跳过远端回执持久化，此参数禁止用于正式无人值守云端运行。

## 持久数据

报告：`reports/YYYY-MM-DD.md`。新版本使用`reports/YYYY-MM-DD.vVERSION.md`，原稿不覆盖。版本由完整研究JSON与报告内容生成，同一输入重复归档不重复历史行。

推荐历史：`data/recommendation_history.csv`，原十二字段加数据基准日及版本。B/C类观察股不填可执行买入区间；无候选、休市、数据不足不伪造股票行。

后续表现：`data/performance_history.csv`，由研究任务基于可核验行情追加5/10/20个交易日观察收盘表现和触发证据。日线高低点不能证明实际成交，未证实触发记“未确认”。

原始研究、摘要、manifest和delivery回执：`data/runs/研究日期/版本/`。来源快照和模型输入：`data/evidence/研究日期/版本/`。

## 失败处理

发送状态包括prepared、pending、sent、failed、unknown。明确业务失败最多三次尝试；超时、断连、HTTP 5xx、无法识别的状态不自动重发。pending/unknown表示需要核查；下次任务不得自动重置回执。HTTP成功不等于飞书业务成功。

如果报告保存成功但推送失败，保留原研究和回执，独立报告失败原因。外部推送成功但回执push失败时，不重新发送，以远端pending状态提示待核查。

测试中的股票数值均为虚构样本，只在临时目录使用；测试不联网、不发送真实消息、不写入正式推荐历史。
