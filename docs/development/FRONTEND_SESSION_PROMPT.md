# 前端开发会话启动提示

将下面内容作为前端对话的第一条任务指令使用。

---

你负责 AI Data Analyst Agent 的前端开发。

开始前必须完整阅读：

1. `docs/README.md`
2. `docs/api/openapi.yaml`
3. `docs/api/API_INTEGRATION_STANDARD.md`
4. `docs/development/PARALLEL_DEVELOPMENT_PLAN.md`
5. `docs/development/TECH_STACK_DECISION.md`

工作边界：

- 主要修改 `frontend/**`。
- 不修改 `backend/**`。
- 不自行发明接口、字段、枚举、状态或错误码。
- `docs/api/**` 是共享契约；如需修改，先说明原因和兼容性，并同时更新 `CONTRACT_CHANGELOG.md`。
- 使用 OpenAPI 生成或集中维护 API 类型；页面组件不得重复手写响应类型。
- 后端未完成时，依据 OpenAPI 示例建立 Mock，不改变正式数据结构。
- 所有异步操作统一使用 Job 状态机和轮询规范。
- 每个页面必须处理 loading、empty、error、blocked、success 状态。
- 不将 mock、临时兼容字段或 `any` 作为完成方案。

当前任务顺序：

```text
FE-001 → FE-002 → FE-003 → FE-004 → FE-005 → FE-101 → FE-102
```

每完成一项：

1. 运行类型检查、测试和构建。
2. 更新 `PARALLEL_DEVELOPMENT_PLAN.md` 中对应状态。
3. 报告使用到的 operationId。
4. 如发现契约问题，提交“契约变更请求”，不要静默绕开。

本轮完成标准：

- 前端工程可以启动。
- API Base URL 可配置。
- 统一 API Client、错误解析和 Job 轮询可复用。
- 项目创建和文件上传页面可在 Mock 模式完成完整交互。
- 测试覆盖成功、失败、超限、取消和刷新恢复。

先检查仓库现状，再实施，不要覆盖其他会话的更改。

---
