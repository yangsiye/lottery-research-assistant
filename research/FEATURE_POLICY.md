# Feature policy：统一而不打架

## A. 球级状态特征

1. Frequency family：freq_10/20/30/50/100、window z-score。
2. Recency family：omission、omission ratio/z-score、指数衰减频率。
3. Trend family：短期减长期频率。
4. Bayesian family：理论概率先验下的收缩均值。
5. Relation family：last-draw、neighbor-last、same-tail-last、transition lift。
6. Interval family：历史出现间隔均值和CV。

**政策：**这些都是观测量，不带“应该追/应该杀”的方向。模型学习其方向。

## B. 组合结构特征

和值、跨度、奇偶、大小、三区、012路、连号、同尾、质数数量、AC值、重号数、邻号数。

**政策：**生产阶段只允许 soft score；不得做一刀切过滤。

## C. 明确禁止的生产信号

- 五行、生肖、天干地支、梅花易数；
- “某号该出了”式赌徒谬误；
- 事后挑选规则；
- 未经样本外验证的神经网络输出；
- 用中奖金额/一次大奖作为唯一优化目标。

## D. 去重与冲突控制

- 同一概念的不同表达归入一个 family，不重复计票。
- 模型之间允许存在不同函数形式，但融合权重来自 OOS 指标，不靠主观“各占20%”。
- 结构分最多占最终候选排序的10%，且不删除候选。
- 如果所有学习模型都未优于 Uniform，则 Ensemble 退回 Uniform，而不是强行使用AI。
