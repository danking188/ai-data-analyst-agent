# API 对接规范

版本：1.0  
状态：开发基线  
机器可读契约：[`openapi.yaml`](./openapi.yaml)

## 1. 适用范围

本规范适用于 AI Data Analyst Agent 的 Web 前端、应用 API、异步任务执行器以及导出下载流程。OpenAPI 描述具体路径和字段，本文件规定跨接口通用行为。

## 2. 基础约定

- API 前缀：`/api/v1`
- 数据格式：除文件上传和文件下载外统一使用 `application/json`
- 字符编码：UTF-8
- 字段命名：JSON 使用 `snake_case`
- 时间格式：ISO 8601 UTC，例如 `2026-07-09T08:30:00Z`
- 日期格式：`YYYY-MM-DD`
- 布尔值：只使用 `true`、`false`
- 空值：仅字段语义允许缺失时返回 `null`；不使用空字符串代替 `null`
- 金额与高精度小数：字符串传输，避免浮点精度损失
- 比例：使用 `0–1` 小数，例如 `0.0584`，页面自行格式化为 `5.84%`
- 标识符：不向客户端假定自增整数；均作为不透明字符串处理
- 未在 OpenAPI Schema 中声明的响应字段，前端不得依赖

## 3. 鉴权与项目隔离

- 默认使用 `Authorization: Bearer <token>`。
- `/health` 不要求鉴权；其他接口默认要求鉴权。
- 项目资源使用路径级隔离：`/projects/{project_id}/...`。
- 后端必须校验当前用户对 `project_id` 的权限，不能只依赖前端隐藏入口。
- 管理员默认不获得数据明文访问权；内容权限与系统管理权限分离。
- 返回 `404` 时可以同时用于资源不存在和当前用户无权获知资源存在，避免枚举。

## 4. 标准响应

成功响应直接返回 OpenAPI 中声明的资源对象，不再额外嵌套 `data`。

集合响应统一为：

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 0,
  "has_more": false
}
```

错误响应统一为：

```json
{
  "error": {
    "code": "SCHEMA_CONFLICT",
    "message": "字段定义与当前数据版本不兼容",
    "request_id": "req_01J...",
    "retryable": false,
    "details": {
      "column": "zip_code"
    }
  }
}
```

规则：

- `message` 可直接展示给用户，但前端仍应按 `code` 决定交互。
- `details` 只放结构化诊断信息，不返回堆栈、密钥、系统路径或原始敏感值。
- `request_id` 必须能关联后端日志。
- `retryable=true` 只表示技术上可重试，不代表前端必须自动重试。

## 5. HTTP 状态码

| 状态码 | 使用场景 |
|---|---|
| `200` | 查询、同步更新、取消成功 |
| `201` | 同步创建资源成功 |
| `202` | 已接收异步任务，返回 `Job` |
| `204` | 无响应体的成功操作 |
| `400` | JSON/参数格式错误 |
| `401` | 未登录或凭证失效 |
| `403` | 已识别用户但无操作权限 |
| `404` | 资源不存在或不可见 |
| `409` | 状态冲突、重复操作、版本冲突 |
| `412` | `If-Match`/前置条件不满足 |
| `413` | 上传文件超过限制 |
| `415` | 不支持的媒体或文件类型 |
| `422` | 业务校验失败，格式正确但不能执行 |
| `429` | 频率或资源配额超限 |
| `500` | 未处理的服务错误 |
| `502/503` | 依赖服务或执行器不可用 |
| `504` | 上游或执行任务超时 |

## 6. 错误码命名

采用 `<领域>_<原因>` 大写格式。首批稳定错误码：

| 错误码 | HTTP | 含义 |
|---|---:|---|
| `AUTH_REQUIRED` | 401 | 需要登录 |
| `PERMISSION_DENIED` | 403 | 无操作权限 |
| `RESOURCE_NOT_FOUND` | 404 | 资源不存在或不可见 |
| `VALIDATION_ERROR` | 422 | 通用业务校验失败 |
| `STATE_CONFLICT` | 409 | 当前状态不允许操作 |
| `VERSION_CONFLICT` | 412 | 资源版本与客户端不一致 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一幂等键对应不同请求 |
| `FILE_TOO_LARGE` | 413 | 文件超过限制 |
| `UNSUPPORTED_FILE_TYPE` | 415 | 文件类型不支持 |
| `FILE_CORRUPTED` | 422 | 文件损坏或无法解析 |
| `ENCRYPTED_WORKBOOK` | 422 | Excel 已加密 |
| `SHEET_REQUIRED` | 422 | 需要选择工作表 |
| `SCHEMA_CONFLICT` | 422 | Schema 定义冲突 |
| `LOW_CONFIDENCE_CONFIRMATION_REQUIRED` | 422 | 低置信度字段尚未确认 |
| `CLEANING_APPROVAL_REQUIRED` | 409 | 清洗计划未批准 |
| `INVARIANT_VIOLATION` | 422 | 清洗后数据不变量失败 |
| `ANALYSIS_SPEC_INCOMPLETE` | 422 | 分析定义不完整 |
| `LEAKAGE_RISK_UNRESOLVED` | 422 | 高风险泄露候选未处置 |
| `INSUFFICIENT_SAMPLE` | 422 | 样本量或类别不足 |
| `CLAIM_VALIDATION_FAILED` | 422 | 结论验证失败 |
| `ARTIFACT_NOT_READY` | 409 | 产物尚未生成 |
| `JOB_NOT_CANCELLABLE` | 409 | 任务已进入不可取消状态 |
| `RATE_LIMITED` | 429 | 请求过多 |
| `EXECUTOR_UNAVAILABLE` | 503 | 执行器不可用 |

新增稳定错误码必须同步修改 OpenAPI 和变更记录。

## 7. 分页、筛选与排序

- 页码从 `1` 开始。
- 默认 `page_size=20`，最大 `100`。
- 排序参数：`sort=<field>:asc` 或 `sort=<field>:desc`。
- 多值过滤使用重复参数，例如 `status=ready&status=failed`；具体可用字段以 OpenAPI 为准。
- 列表必须返回 `total` 和 `has_more`。
- 前端切换筛选条件后必须将页码重置为 `1`。
- 大数据预览不是普通分页：使用稳定的 `cursor`，避免数据变化导致重复或遗漏。

## 8. 幂等、并发与资源版本

- 所有会创建任务或版本的 `POST` 接口必须接受 `Idempotency-Key`。
- 同一用户、同一路径、同一请求体在 24 小时内重复提交相同幂等键，应返回同一资源或任务。
- 同一幂等键对应不同请求体，返回 `409 IDEMPOTENCY_CONFLICT`。
- 可编辑资源返回整数 `revision`。
- 更新关键配置时前端发送 `If-Match: "<revision>"`；不匹配返回 `412 VERSION_CONFLICT`。
- DatasetVersion、AnalysisRun、Artifact 和已被 Run 引用的 AnalysisSpec 修订不可原地改写。

## 9. 异步任务

文件解析、质量扫描、清洗执行、EDA、建模、报告导出等耗时操作返回 `202` 和 `Job`：

```json
{
  "job_id": "job_01J...",
  "kind": "quality_scan",
  "status": "queued",
  "progress": 0,
  "current_step": null,
  "resource_type": "quality_scan",
  "resource_id": null,
  "created_at": "2026-07-09T08:30:00Z",
  "updated_at": "2026-07-09T08:30:00Z",
  "error": null
}
```

状态机：

```text
queued → running → succeeded
                 ↘ failed
queued/running → cancelling → cancelled
running → blocked
```

轮询规则：

- MVP 使用 `GET /jobs/{job_id}` 轮询。
- 前 30 秒每 1 秒一次，之后每 3 秒一次；页面在后台时降至每 10 秒一次。
- `succeeded` 后根据 `resource_type/resource_id` 获取结果。
- `failed/cancelled/blocked` 为终态，不再自动轮询。
- `retry_after_ms` 非空时优先采用后端建议。
- 网络错误可指数退避重试；业务终态不得自动重新提交任务。

SSE/WebSocket 不作为 MVP 依赖；未来引入时不得改变 Job 的持久状态语义。

## 10. 文件上传与下载

上传：

- 使用 `multipart/form-data`，字段名为 `file`。
- 文件名只用于展示，后端必须生成安全存储名。
- 支持 `.csv`、`.xls`、`.xlsx`、`.parquet`。
- 默认建议上限 500 MB，最终值由部署配置决定并通过 `/system/capabilities` 返回。
- 上传成功不代表解析成功；成功创建上传任务后继续通过 Job 获取 DatasetVersion。
- CSV 解析参数、Excel Sheet 选择通过独立接口确认，不在文件名中编码。

下载：

- 导出接口先创建 Export/Artifact，再返回有时效的 `download_url`。
- 下载地址不得作为永久资源标识；过期后重新获取。
- `Content-Disposition` 中提供安全文件名。
- 导出必须执行项目权限和敏感字段策略。

## 11. 数据版本与证据规则

- 所有分析、质量、清洗、Artifact 和 Claim 都必须携带 `dataset_version_id`。
- 切换项目的当前版本不会改写历史对象绑定。
- 跨版本比较必须显式传入两个版本 ID，不允许后端隐式使用“当前版本”替换。
- 报告正式结论只接受 `validation_status=passed` 的 Claim。
- 图表、指标和模型结果必须通过 Artifact 暴露来源工具、参数和输入版本。

## 12. Mock 与前端开发

- `openapi.yaml` 中的 `example/examples` 是前端 Mock 的基础。
- Mock 数据必须使用明显的虚构 ID 和内容，不复制真实用户数据。
- 前端应覆盖 `loading / empty / partial / blocked / failed / succeeded` 状态。
- Mock 与真实接口切换不得改变组件的数据类型。
- 后端未完成时，前端可以 Mock；不得因此修改本地字段名绕开契约。

## 13. 契约变更

变更分级：

- Patch：新增可选字段、示例、说明，不破坏现有调用。
- Minor：新增接口或能力，旧调用仍可用。
- Breaking：删除/重命名字段、修改类型、改变状态语义或必填性。

流程：

1. 在 `openapi.yaml` 提交变更。
2. 在 `CONTRACT_CHANGELOG.md` 说明原因、前端影响、后端影响和迁移方式。
3. 两端确认后修改实现。
4. 契约校验、后端契约测试、前端类型检查全部通过。
5. Breaking change 必须提升 API 主版本或提供兼容期。

口头约定和聊天记录不能替代上述流程。

## 14. 联调完成定义

一个接口只有同时满足以下条件才算完成：

- OpenAPI 已定义请求、响应、错误与示例。
- 后端实现通过契约测试和权限测试。
- 前端已移除对应临时 Mock 或明确保留为测试夹具。
- loading、empty、error、retry 和 success 状态均已验证。
- request_id 可在前后端日志中关联。
- 敏感数据、跨项目访问和异常状态已测试。
- 对应任务在并行计划中更新为完成。

