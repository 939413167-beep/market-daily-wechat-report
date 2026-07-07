# market-daily-wechat-report

每天 A股和美股收盘后生成 Markdown 收盘报告，并通过微信推送。当前是第一阶段 MVP，支持 Server酱 Turbo 和 PushPlus。

## 功能

- A股：主要指数、涨跌幅、成交额、市场宽度、涨跌停数量、领涨/领跌板块、半导体/CPO/AI/机器人等重点方向、简短总结。
- 美股：道琼斯、纳斯达克、标普500，NVDA/AAPL/MSFT/TSLA/META/GOOGL，VIX、美元指数、10年美债收益率，以及对次日 A股科技方向的观察提示。
- 推送：通过 `PUSH_CHANNEL` 在 `serverchan` 和 `pushplus` 之间切换，也可以设为 `none` 只生成报告。
- 去重：以“市场 + 交易日”为键写入 `state/push_log.json`，避免同一市场同一交易日重复推送。
- 异常提醒：数据获取或报告生成失败时，会尝试向微信发送失败提醒。
- 报告归档：生成的 Markdown 会保存到 `reports/`。

## 目录结构

```text
market_daily_wechat_report/
  data/                  # AKShare/yfinance 数据适配器
  config.py              # 环境变量配置
  dedupe.py              # 去重状态
  main.py                # 命令行入口
  models.py              # 报告数据结构
  push.py                # Server酱 / PushPlus 推送
  report.py              # Markdown 渲染与保存
reports/                 # 每日报告
state/                   # 去重状态
tests/                   # pytest 测试
.github/workflows/       # GitHub Actions 定时任务
```

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Windows PowerShell 可使用：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`：

```text
PUSH_CHANNEL=serverchan
SERVERCHAN_SENDKEY=你的_Server酱_SendKey
PUSHPLUS_TOKEN=
```

或使用 PushPlus：

```text
PUSH_CHANNEL=pushplus
SERVERCHAN_SENDKEY=
PUSHPLUS_TOKEN=你的_PushPlus_Token
```

本地调试推荐先使用 dry-run。dry-run 会正常获取数据、生成并保存 Markdown，但不会调用 Server酱 / PushPlus，也不会写入正式去重状态：

```bash
python -m market_daily_wechat_report.main --market ashare --dry-run
python -m market_daily_wechat_report.main --market us --dry-run
```

单独验证推送通道：

```bash
python -m market_daily_wechat_report.main --test-push
```

`--test-push` 只发送一条极短测试消息，不拉取 A股 / 美股数据，也不生成正式报告。

真实推送命令：

```bash
python -m market_daily_wechat_report.main --market ashare
python -m market_daily_wechat_report.main --market us
```

默认命令会同时获取 A股和美股数据，并只推送一份综合报告，避免本地调试时连续消耗多次推送额度：

```bash
python -m market_daily_wechat_report.main
```

如果显式分别执行 A股和美股真实推送命令，会消耗两次微信推送额度。Server酱可能有每日发送次数限制，本地调试应优先使用 `--dry-run`。

## GitHub Secrets

在 GitHub 仓库中进入 `Settings -> Secrets and variables -> Actions -> New repository secret`，添加：

```text
PUSH_CHANNEL=serverchan
SERVERCHAN_SENDKEY=你的_Server酱_SendKey
PUSHPLUS_TOKEN=你的_PushPlus_Token
```

只使用其中一个推送通道时，另一个 token 可以不配置。不要把真实 token 写入代码、README 或提交记录。

## GitHub Actions 定时

工作流文件位于 `.github/workflows/daily-report.yml`。

- A股：`30 7 * * 1-5`，对应北京时间/台北时间 15:30。
- 美股：`30 21 * * 1-5` 和 `30 22 * * 1-5`，覆盖美国夏令时和冬令时。
- 手动触发：支持 `workflow_dispatch`，可选择 `auto`、`a`、`us`，也可选择是否真的推送。

GitHub Actions 的 cron 使用 UTC 时间。美股两个触发点都会进入代码内部交易日和去重判断，避免同一交易日重复推送。

## 测试

```bash
pytest
```

当前测试覆盖报告渲染、去重和空推送通道。行情接口测试没有默认联网执行，避免 CI 因外部数据源波动而失败。

## 注意

- AKShare 和 yfinance 都依赖外部数据源，字段或可用性可能变化；如果数据源临时失败，程序会生成包含“数据源状态”的降级或部分报告。
- A股节假日优先使用 AKShare 交易日历判断；交易日历获取失败时，会退回到工作日判断。
- 美股报告使用 yfinance 最近日线数据，并以返回的最新交易日作为去重日期。
