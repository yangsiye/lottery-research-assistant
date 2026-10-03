# 彩票研究助理（双色球 + 大乐透）· 彩票1.5版

这是为 Codex / Python 准备的长期彩票研究工程。**原先确认的六块能力全部保留**，`ssq-fusion` / `dlt-fusion` 只作为规律实验室和验证体系的增强来源，不替代主架构。

## 六模块

1. **每日数据研究**：真实数据同步、校验、多时间窗口、全链路留痕。
2. **规律实验室**：吸收多窗口、z-score、遗漏、重/邻/连号、三区、012、AC等，但所有方向性经验统一变成可学习特征。
3. **模型动物园**：Uniform/Bayes/Logistic/Gradient Boosting为生产锚点；深度学习和新GitHub模型先进挑战者池。
4. **每日进化**：严格按时间顺序样本外表现更新权重，支持晋级、降权、退役和回滚。
5. **开奖前单一输出**：每个彩种每期开奖日输出一组主推荐与模型版本。
6. **开奖后复盘**：冻结预测→对奖→归因→滚动回测→显著性/稳定性检查→更新。

研究员模式横跨六模块：每天搜索新方法，但不能绕过验证直接改生产推荐。

## 统一而不打架

不再并列执行“追热”“追冷”“遗漏回补”“避开上期号”“追重号”等互相可能矛盾的规则。它们被统一编码为频率、遗漏、趋势、last-draw、neighbor、transition 等观测特征；由模型在 walk-forward / holdout 中学习其方向和有效性。

组合结构（和值、跨度、奇偶、大小、三区、012、连号、同尾、AC等）只占候选排序的小权重，**不硬删组合**。

## 当前生产模型

- Uniform random baseline
- Empirical Bayes frequency shrinkage
- Regularized Logistic Regression
- Histogram Gradient Boosting
- 动态样本外加权 Ensemble

XGBoost、LightGBM、CatBoost、HMM、LSTM、GRU、Transformer、RL、遗传算法等属于挑战者池，只有通过严格样本外门槛才晋级。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m lottery_assistant.cli init-db
```

## 运行

```bash
python -m lottery_assistant.cli sync ssq --periods 500
python -m lottery_assistant.cli sync dlt --periods 500
python -m lottery_assistant.cli recommend ssq
python -m lottery_assistant.cli recommend dlt
```

## 数据库

`data/lottery.db` 保存开奖记录、预测、对奖、模型运行、研究候选、模型进化记录。

## 文档

- `research/SIX_MODULE_ARCHITECTURE.md`：六模块总纲
- `research/FEATURE_POLICY.md`：指标统一/冲突消解
- `research/MODEL_GOVERNANCE.md`：挑战者晋级与模型治理
- `research/INITIAL_RESEARCH_BASELINE.md`：首版研究基线

## 数据安全原则

官方接口调整或数据无法校验时直接报错；不用模拟开奖数据顶替真实数据。


## Cloud Edition（无 GitHub）

见 `CLOUD_DEPLOY_PYTHONANYWHERE.md`。云端主运行器：`python -m lottery_assistant.cloud`。

## GitHub Actions Cloud Edition v1.3

本版本不需要 PythonAnywhere，也不依赖 ChatGPT 的 GitHub Connector。
只要把仓库内容上传到 GitHub，`.github/workflows/lottery-cloud.yml` 会在北京时间 08:30 / 15:30 / 23:00 自动运行六模块系统并持久化 SQLite 状态。

详见 `GITHUB_ACTIONS_DEPLOY.md`。


## 1.5 冻结与复盘闭环

规则依据见 `research/RULES_REFERENCE.md`，验收协议见 `research/ACCEPTANCE_V1_5.md`。官方数据不足时停止推荐；同一开奖日保持同一份冻结记录。bridge 1.2 区分休市、未开奖、数据错误和过期。
