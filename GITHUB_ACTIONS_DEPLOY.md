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

- 08:30：研究员晨研 + 双色球/大乐透数据同步
- 18:30：开奖日才生成对应彩种的一组主推荐
- 23:30：同步开奖结果 + 自动复盘

GitHub Actions 的 schedule 使用 `timezone: Asia/Shanghai`。

## 状态如何保存

GitHub runner 每次都是新虚拟机，因此工作流结束时会自动把以下状态提交回仓库：

- `data/lottery.db`：SQLite 长期状态
- `reports/`：最新推荐、复盘、云端运行结果
- `bridge/latest.json`：人类可读状态页
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
- Build human-readable status page
- Persist database, reports and research state

如果当天不在相应彩种开奖日，18:30 的运行可能只显示无对应推荐，这是正常行为。
