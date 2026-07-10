# API 契约变更记录

所有影响前后端对接的变更必须记录在此。最新记录放在最上方。

## Unreleased

### Changed

- `Artifact.run_id` 允许为 `null`，用于清洗预览、版本比较等不隶属于 AnalysisRun 的产物。
- 兼容性：Patch。

### Frontend impact

- Artifact 查看器需要把 `run_id` 视为可空字段。

### Backend impact

- 后端 Artifact schema 与现有持久化模型保持一致。

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
