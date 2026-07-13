# API 契约变更记录

所有影响前后端对接的变更必须记录在此。最新记录放在最上方。

## Unreleased

- 新增 `GET /projects/{project_id}/assistant/metrics`，返回近 1~90 天的 Turn 成功/
  失败数、Token、平均与 P95 延迟，以及工具成功、失败和拒绝数。

### Added

- 新增 `PATCH /projects/{project_id}/assistant/tool-calls/{tool_call_id}`，用于在批准前编辑并重新校验受控工具参数。
- `AssistantToolCall` 增加结构化 `arguments`、确定性 `result` 和结果资源链接。
- Assistant 确认计划可通过现有 Worker 创建真实 AnalysisSpec、AnalysisRun、CleaningPlan、DatasetVersion 和特征建议 Artifact。
- 新增 Assistant v0 契约：项目会话、消息、计划确认、重试、取消和回答反馈。
- 新增结构化 `AssistantPlan`、`AssistantAnswer`、证据引用和工具调用状态。
- `Job.kind` 增加 `assistant_turn`，用于后续异步大模型编排。
- `SystemCapabilities.llm` 分别声明 `evidence_narrative` 和 `assistant`；P1 只开启证据解读，Assistant 在 P2 完成前保持关闭。
- 报告导出格式增加 `ai_narrative`，异步生成绑定 Artifact/Claim 的结构化证据解读 Artifact。
- 兼容性：Minor。现有接口和字段保持兼容。

### Changed

- `Artifact.run_id` 允许为 `null`，用于清洗预览、版本比较等不隶属于 AnalysisRun 的产物。
- 兼容性：Patch。

### Frontend impact

- Artifact 查看器需要把 `run_id` 视为可空字段。
- 重新生成 API 类型；Assistant 页面只在能力开关为 `true` 时启用。

### Backend impact

- 后端 Artifact schema 与现有持久化模型保持一致。
- LLM-0 Provider 基础和 LLM-1 证据型解读已实现；Assistant 路由、持久化和 `assistant_turn` Worker 在 LLM-2 实现。
- `LLM_ENABLED=true` 当前只开放报告页证据解读，不表示对话式 Assistant 已可用。

## 1.0.0 — 2026-07-09

### Added

- 建立 `/api/v1` 契约基线。
- 定义项目、数据集、数据版本、Schema、质量问题、清洗计划、分析定义、运行、任务、Artifact、Claim 和导出接口。
- 统一分页、错误结构、幂等键、异步 Job、资源 revision 和下载规则。

### Frontend impact

- 以 `openapi.yaml` 生成或维护统一 API 类型。
- 所有长任务使用 Job 轮询状态机。
- 页面不得依赖未声明字段。

### Backend impact

- 响应结构、状态码和错误码必须符合 OpenAPI。
- 创建型异步操作支持 `Idempotency-Key`。
- 项目级资源执行权限隔离。

---

## 变更模板

复制以下模板并填写：

```markdown
## x.y.z — YYYY-MM-DD

### Changed
- 变更内容：
- 变更原因：
- 兼容性：Patch / Minor / Breaking

### Frontend impact
- 

### Backend impact
- 

### Migration
- 
```
