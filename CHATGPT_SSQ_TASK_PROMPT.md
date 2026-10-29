# 双色球16:00任务提示词

此文本用于更新已有“彩票1.5版·双色球推送”任务，不新建重复任务。调度保持北京时间每周二、周四、周日16:00，休市由后台日历判定。修改后须重新打开任务并核对保存的提示词和调度；保存配置不等于实际投递已验证。

```text
北京时间16:00执行彩票1.5版双色球推送，时区Asia/Shanghai。只转发yangsiye/lottery-research-assistant后台已正式冻结的一组双色球推荐，不自行选号、不重新计算、不改号码、不用旧期代替。

一、读取与一致性
优先用已连接GitHub获取仓库main当前提交SHA，再以该SHA读取bridge/ssq.json和bridge/latest.json。不得用缓存Pages或搜索摘要。两个文件须来自同一提交，双色球recommendation、publication与latest.ssq、latest.publications.ssq须一致；若发现读取期间main变更，重新取得同一提交文件。失败时可有限重读，仍失败则明确报告读取/快照一致性异常，不虚构后台状态。

二、后台发布决定
使用schema_version1.3的publication（与latest.publications.ssq一致）。仅publication.status=READY、其正式记录校验通过，且对应recommendation完整一致时才可发布。schema/字段缺失或校验失败须报告具体异常，不自行臆测READY。
核验北京时间今天是后台日历允许的开奖日、draw_state.as_of_date和recommendation.target_draw_date均为今天、draw_state=WAITING_DRAW、没有官方休市/已开奖状态；核验lottery=ssq、prediction_id、basis_issue、frozen_at、model_version、freeze_sha256、target_issue_key、dedupe_key及valid_until一致。红球须为1至33内6个互不重复整数，蓝球为1至16内1个整数。当前时间不得早于冻结时间，也不得达到valid_until；北京时间20:00及以后不补发号码。若非开奖日或HOLIDAY_SUSPENDED，按正常日历状态简述，不报任务缺失。

三、时效与异常必须分开
bridge_health的运行时间、generated_at和BRIDGE_STALE仅说明运行/快照风险，不能单独推翻校验通过且在有效期内的今天正式冻结记录。尤其不得发明“必须15:30后生成/运行”或“一两小时前冻结就失效”的门槛：2026-10-29的14:06正式冻结prediction_id15在16:03仍应通过有效期核验。若publication=READY，正常转发并披露相关运行告警。主接口403、单一官方备用源、晨报/研究或大乐透partial分别披露；只有具体影响当前双色球正式记录校验或数据一致性的错误才作为该记录的阻断原因。没有正式记录时明确报告“系统未按时产出”；已有记录但被校验阻断时写明“已有冻结记录，因某项具体校验未通过”，不要混淆两者。

四、去重与回执
先读取本任务/对话可获取的以往正式推送结果，按publication.dedupe_key，并联合lottery、target_issue_key和prediction_id核对。任一相同期身份或prediction_id已正式发布则不重复发号码；同一期出现不同冻结内容/哈希则报告冲突。仅出现异常报告、冻结存在说明或开奖复盘，均不算号码已发送；recent_reviews不是推送回执。历史无法读取时明确报告“去重状态无法确认”，不宣称未发送或已发送，不产生伪回执。未确认去重前不补发号码。
首次核验通过的正式推送末尾保留可审计回执：lottery、target_draw_date、target_issue_key、basis_issue、prediction_id、dedupe_key、freeze_sha256、frozen_at、model_version和读取的GitHub提交SHA。不得在发布前登记为已送达，不把代码检查/演练标为正式推送。当前对话回执不能证明跨系统恰好一次投递。

五、输出
用中文简洁呈现一组红球、蓝球、冻结时间、模型版本、生产模型权重和重要异常；模型分数不等于实际中奖概率，挑战模型未通过既定样本外治理不得晋级。附本次读取提交的源文件链接。正常重复或休市不反复告警；缺少正式产出、校验失败、读取失败、去重未知等明确报告原因，不静默、不以旧号码填补。
```
