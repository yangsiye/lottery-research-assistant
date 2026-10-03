# 使用方式：ChatGPT 是唯一前台

你不需要打开 GitHub Pages，也不需要在网页里看推荐号码。

后台由 GitHub Actions 负责：
- 08:30 数据同步 + 研究员模式
- 15:30 开奖日计算推荐
- 23:00 开奖后同步 + 复盘

后台每次运行后只生成 `bridge/*.json` 机器文件。ChatGPT 定时任务在稍后读取这些文件，并在 ChatGPT 对话中推送号码、复盘与模型变化。

首次部署后，把仓库 URL 发给 ChatGPT 一次，用于绑定 raw JSON 地址。之后用户交互均留在 ChatGPT。
