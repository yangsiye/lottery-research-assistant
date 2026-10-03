# Initial research baseline — revised 2026-10-03

## 原六模块保持不变

1. 每日数据研究
2. 规律实验室
3. 模型动物园
4. 每日进化
5. 开奖前单一最终输出
6. 开奖后复盘与进化

研究员模式作为跨模块研发机制，不替代六模块。

## 从 ssq-fusion / dlt-fusion 吸收

- 多窗口统计与窗口共识；
- 频率 z-score、遗漏与遗漏压力；
- 主区/副区独立分析，特别是双色球蓝球独立引擎思想；
- 和值、跨度、三区、奇偶、大小、012、连号、重号、邻号、同尾、质合、AC等结构画像；
- 随机基线；
- 推荐留痕、开奖后对奖；
- Wilson/二项检验思想；
- predict → archive → analyze → iterate 的自学习闭环。

## 不直接照搬的部分

- 热号阵列、遗漏狙击、冷号追号；
- “避开前一期号码”之类固定铁律；
- 奇偶连续后必反转、均值必回归等确定性说法；
- 玄学维度进入生产模型；
- 多策略各自打分后简单投票。

这些内容若有可计算信息，只转成**无方向特征**，由严格样本外验证决定贡献。

## 统一决策

1. Hot continuation 与 cold rebound 不再是两个策略：统一编码为频率、z-score、遗漏、趋势和Bayes收缩。
2. Repeat 与 avoid-repeat 不再冲突：`last_draw` / `repeat_prev` 只作为特征。
3. Neighbor、same-tail、transition 等关系只作为特征，不预设正负方向。
4. Sum/span/odd-even/012/三区/AC等只做结构soft score，不硬删组合。
5. 双色球/大乐透独立训练；主区/副区独立训练；验证治理框架统一。
6. 新 ML/DL 先进 challenger pool；未超过简单基线则不进入生产。
7. 如果所有学习模型都不优于 Uniform，生产层回退 Uniform。
