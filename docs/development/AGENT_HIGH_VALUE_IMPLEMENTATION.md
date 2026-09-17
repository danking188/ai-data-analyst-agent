# Agent 高价值能力实施记录

最后更新：2026-09-17

本轮不引入自由聊天式 Multi-Agent 或通用向量 RAG，而是实现当前评测和线上
架构能够证明有直接收益的六项能力。

## 1. 结构化记忆

- 会话状态、显式用户偏好、已验证工具资源和待确认决策分开存储。
- 可验证事实只记录资源标识，不把上传单元格或历史自由文本重新当成
  system instruction。
- 每个项目带来源、数据版本、可信等级、生成时间和过期时间。
- 会话切换数据版本后，旧版本事实立即失效；项目成员可查看或清空记忆。

## 2. 结构化数据语义层

- 新增项目级 Semantic Metric API 和前端“语义指标”页签。
- 指标只允许 `sum/average/minimum/maximum/count/distinct_count` 安全聚合，
  不接受 SQL、Python 或任意表达式。
- 指标绑定数据版本、来源字段、单位和聚合粒度，禁止直接使用敏感列。
- Schema 被修改且与指标冲突时，指标自动转为 `stale`；Agent 只检索当前
  版本的 `active` 指标。

## 3. 候选 Prompt/模型真实重放

- 原有 `/trace/replay` 继续负责无副作用状态校验。
- 新增 `/trace/compare`，固定原问题和已记录工具结果，但允许替换经白名单
  授权的模型或 `current/concise/evidence_auditor` Prompt 变体。
- 重放不执行工具或写操作，返回引用校验、Token、延迟和与原回答的相似度。
- `LLM_REPLAY_ALLOWED_MODELS` 限制可选候选模型，默认只允许当前生产模型。

## 4. Durable execution 检查点

- 受控写工具在创建资源后、启动子 Worker 前持久化 execution receipt。
- Worker 在资源已创建但工具未写入终态时中断，会从 receipt 继续原子任务，
  不再创建第二个 AnalysisRun、CleaningPlan、DatasetVersion 或报告任务。
- 已完成工具在 Turn 恢复时作为已知资源继续传递，不重复执行。

## 5. 能力分级和红队边界

- 每个 Agent 工具显式声明 `read/reversible_write/irreversible_write`、项目绑定、
  确认要求和 dry-run 能力。
- 只读阶段不能调用写工具；写工具在未确认时会被能力层再次拒绝。
- 红队测试覆盖未知工具、跨权意图、伪造引用、表格公式、恶意文件名、
  Prompt Injection 和无界资源请求。

## 6. Bad Case 闭环

- `export_agent_bad_cases.py` 汇总差评反馈和失败 Agent Run。
- 导出前会截断文本并脱敏密钥、Bearer Token 和邮箱，输出可转入评测用例审核。
- 失败分类、模型和 Prompt 版本与原运行保持关联。

## 明确不做

- 不为了形式增加 Multi-Agent；只有当评测证明专业角色分工改善某类稳定失败时
  才引入。
- 不用向量 RAG 替代结构化 Artifact、Claim、Schema 和 Semantic Metric 检索。
- 不在每次 CI 提交中运行昂贵且非确定的真实模型全量评测。
