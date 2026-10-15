# A股每日低估值选股与交易计划

Codex原生云端研究任务配置与报告归档/飞书摘要工具。每天Asia/Shanghai 08:30开始，公开数据优先，每次独立研究；先经营质量和估值，后技术入场条件。不进行真实交易。

**当前状态：原生云端任务已创建，因完整验收未通过而保持暂停。** 任务ID为`6ad0c5a545208190b13960f569bc9213`，页面已确认每天08:30、Asia/Shanghai、云端运行。两次手动运行已产生[云端结果](https://chatgpt.com/c/6ad0c66e-619c-83ea-8735-d206049cbb3d)：第二次远端归档成功，但逐股覆盖0只，且没有可用的外部HTTPS POST工具，飞书实际发送0次。不能声称选股和推送全流程已完成，详见[验收记录](docs/cloud-acceptance.md)。

## 运行内容

- `tasks/research.md`：完整十部分研究规则，包含范围、估值、技术形态、风险控制、报告和历史。
- `tasks/cloud-run.md`：提交给Codex原生云端任务的固定执行指令。
- `scripts/workflow.py`：结构化结果校验、版本报告、历史CSV、操作摘要和飞书回执。
- `docs/result-contract.md`：研究结果输入接口。脚本不代替联网数据采集与公司研究。

仓库由用户创建于 `i-meteor-shower/ashare-daily-research`。用户最新确认保持公开；真实Webhook不得提交。报告和历史记录也按仓库存储设置保存。

## 云端配置

1. 使用[已创建的原生云端任务](https://chatgpt.com/scheduled?automationId=6ad0c5a545208190b13960f569bc9213&automationSource=cloud)，不重复创建日程。时间为每天北京时间08:30，永不结束。
2. 原生表单明确说明：设备离线时仍在云端执行，聊天、项目、模型和推理设置不适用于云端任务。表单没有仓库环境或独立秘密变量绑定；专用仓库环境不是本日程的前置条件。
3. 用户已授权将群机器人地址仅保存在该任务的私有提示中。公开仓库只保存无凭据指令；禁止提交Webhook或GitHub令牌。
4. 云端每次使用实际可用的联网工具获取数据，并通过GitHub连接器或真实可用的Git权限读取最新main、保存报告及历史。不能假设继承本机文件、凭据或环境变量。
5. 手动试运行必须验证联网研究、远端归档和飞书业务成功。只有三者完成才启用日程；否则保留暂停并报告具体限制，不建立本地或第三方替代日程。
6. `scripts/workflow.py`只使用Python标准库，支持有Python及Git推送权限的云端执行环境。若通过连接器持久化，可按相同的校验、幂等和回执规则完成；不可用本地测试开关冒充远端持久化。

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
