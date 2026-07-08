# CHANGELOG

## v0.2.0 / Phase 2.1

- 新增 `config/watchlist.yml`，支持配置 A股重点方向关键词和美股关注 ticker。
- A股报告新增【重点方向跟踪】，展示相关板块、平均涨跌幅、最强/最弱板块和状态判断。
- A股报告新增【明日观察】，基于规则生成复盘观察提示。
- 美股报告新增【科技龙头观察】，展示涨幅前三、跌幅前三、AI算力相关和大型科技表现。
- 保留 Phase 1 的 dry-run、降级报告、推送失败日志和美股未收盘跳过推送逻辑。

## v0.1.0 / Phase 1

- 完成 A股、美股基础收盘报告。
- 支持 Server酱 Turbo 和 PushPlus 推送。
- 支持 GitHub Actions 定时运行和手动触发。
- 支持 `.env` 本地配置、GitHub Secrets、降级报告、去重状态和基础 pytest。
