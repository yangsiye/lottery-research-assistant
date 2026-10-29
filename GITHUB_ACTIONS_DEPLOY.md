# GitHub Actions 云端部署（无需 ChatGPT GitHub 连接）

这一版只需要你已有的 GitHub 账号。ChatGPT 的 GitHub 插件是否连接成功，与这里完全无关。

## 最省事的部署方式

1. 登录 GitHub 网页，创建仓库：`lottery-research-assistant-evolution`。
2. 如果你接受代码公开，选择 **Public**：标准 GitHub-hosted Actions 对 public repository 免费。
   如果选择 **Private**：GitHub Free 当前包含每月 2,000 Actions 分钟；本项目按轻量任务设计。
3. 把本 ZIP 解压后的 **所有内容** 上传到仓库根目录。注意 `.github/workflows/lottery-cloud.yml` 也必须上传。
4. 打开仓库 `Actions` 标签。如果 GitHub 要求启用 Actions，点击启用。
5. 打开 `Lottery Research Assistant Cloud` 工作流，点击 `Run workflow` 手动运行一次。
6. 第一次成功后，无需再开手机、Mac、VPN。

## 云端自动时间（北京时间）

- 08:37：研究晨研、官方数据同步；开奖日可以冻结当日正式推荐
- 12:07、14:07、14:37、15:07、15:30、15:45：补同步、冻结重试和推送前健康检查
- 18:45：截止前恢复；20:00之后禁止新建预测
- 23:07、23:37：同步开奖结果及自动复盘重试

工作流使用显式 UTC cron，以上均换算为北京时间（UTC+8）。首次冻结不必等到15:30；已经存在的当日正式冻结记录始终复用，不重选。

GitHub `schedule` 是尽力调度，可能延迟甚至丢弃，不能保证16:00前执行。历史记录已出现连续多小时没有下午运行，因此晨间就允许在核验前一期官方数据后生成当日冻结，并增加多个重试。若需要严格的准时保证，还需独立于GitHub schedule的外部调度器；本仓库没有假定已配置此服务。

15:45之后仍未冻结时，`delivery-readiness-ssq/dlt` 返回 `RECOMMENDATION_MISSING` 并使运行失败；即使晚到的运行已超过20:00，也会明确报告缺失，不再静默成功。休市、非开奖日不告此异常。

## 状态如何保存

GitHub runner 每次都是新虚拟机，因此工作流结束时会自动把以下状态提交回仓库：

- `data/lottery.db`：SQLite 长期状态
- `reports/`：最新推荐、复盘、云端运行结果
- `bridge/latest.json` 等：供ChatGPT读取的机器状态
- `research/`：方法治理文档/研究资料

`permissions: contents: write` + GitHub 自动提供的 `GITHUB_TOKEN` 完成仓库内提交，不需要你创建 Personal Access Token。

## 可选：开启免费网页面板

如果仓库是 Public：

1. Settings → Pages
2. Source 选择 `Deploy from a branch`
3. Branch 选择 `main`，目录选择 `/docs`

之后可通过 ChatGPT bridge 查看推荐和复盘状态。这个步骤不是模型运行所必需。

## 手动验证

Actions → `Lottery Research Assistant Cloud` → `Run workflow`。

成功日志应出现：

- Install dependencies
- Initialize database
- Run due six-module cloud cycle
- Build ChatGPT bridge payload
- Persist database, reports and research state

如果当天不在相应彩种开奖日，运行只显示无对应推荐，这是正常行为。工作流每次从`main`最新状态加载已有冻结；`reports/latest_cloud_run.json`记录触发cron、运行ID、尝试次数、事件提交和实际检出提交，便于区分调度缺失与执行失败。

调度回归验证：`python -m pytest -q tests/test_cloud_schedule.py tests/test_lifecycle.py`。测试只使用临时合成数据库，覆盖晨间冻结、15:30复用、失败重试、成功标记但无冻结、晚到告警和休市跳过。
