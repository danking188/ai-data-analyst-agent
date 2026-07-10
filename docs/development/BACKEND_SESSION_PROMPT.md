# 后端开发会话启动提示

将下面内容作为后端对话的第一条任务指令使用。

---

你负责 AI Data Analyst Agent 的后端开发。

开始前必须完整阅读：

1. `docs/README.md`
2. `docs/api/openapi.yaml`
3. `docs/api/API_INTEGRATION_STANDARD.md`
4. `docs/data/DATA_PERSISTENCE_STANDARD.md`
5. `docs/development/PARALLEL_DEVELOPMENT_PLAN.md`
6. `docs/development/TECH_STACK_DECISION.md`

工作边界：

- 主要修改 `backend/**`。
- 不修改 `frontend/**`。
- 实现必须符合 OpenAPI 的路径、状态码、字段和错误结构。
- 不通过增加未声明字段要求前端“先兼容”。
- `docs/api/**` 是共享契约；如需修改，先说明原因和兼容性，并同时更新 `CONTRACT_CHANGELOG.md`。
- 所有项目资源执行服务端权限校验。
- 创建型异步操作支持 `Idempotency-Key`。
- 可编辑资源实现 revision 和 `If-Match`。
- 长任务持久化为 Job；进程重启后不能遗留虚假的 running 状态。
- 原始数据不可覆盖；正式计算结果必须绑定 DatasetVersion。
- 错误响应不得泄露堆栈、密钥、任意文件路径或敏感数据。

当前任务顺序：

```text
BE-001 → BE-002 → BE-003 → BE-004 → BE-005 → BE-006 → BE-007 → BE-101
```

每完成一项：

1. 运行格式化、类型检查、单元测试和契约测试。
2. 更新 `PARALLEL_DEVELOPMENT_PLAN.md` 中对应状态。
3. 报告已实现的 operationId。
4. 如发现契约问题，提交“契约变更请求”，不要单边改变响应。

本轮完成标准：

- 后端工程可以启动。
- `/health` 与 `/system/capabilities` 符合契约。
- 统一 `ErrorResponse` 和 request_id 生效。
- 数据库迁移、项目 Repository、幂等与 Job 基础可用。
- 项目 CRUD 通过权限、分页、冲突和契约测试。

先检查仓库现状，再实施，不要覆盖其他会话的更改。

---
