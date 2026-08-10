# AI Data Analyst Agent 开发协作入口

本目录是项目开发、契约与发布状态的共享事实源。

## 唯一事实源

1. 产品范围与验收：`product/AI_Data_Analyst_Agent_产品需求规格说明书_V1.0.docx`
2. API 机器可读契约：`api/openapi.yaml`
3. API 全局约定：`api/API_INTEGRATION_STANDARD.md`
4. 契约变更记录：`api/CONTRACT_CHANGELOG.md`
5. 当前项目状态与发布进程：`development/PROJECT_STATUS.md`
6. 技术栈决策：`development/TECH_STACK_DECISION.md`
7. 数据持久化与数据库设计：`data/DATA_PERSISTENCE_STANDARD.md`
8. 历史并行开发基线：`development/PARALLEL_DEVELOPMENT_PLAN.md`
9. 界面设计参考：`design/`
10. 大模型能力扩展计划：`development/LLM_EXTENSION_PLAN.md`
11. 大模型接入架构决策：`development/LLM_ARCHITECTURE_DECISION.md`
12. 正式发布证据模板：`deployment/RELEASE_EVIDENCE.md`

发生冲突时，优先级为：

```text
已批准的契约变更
  > openapi.yaml
  > API_INTEGRATION_STANDARD.md
  > DATA_PERSISTENCE_STANDARD.md
  > 当前项目状态与发布进程
  > 历史并行任务计划
  > 对话中的临时描述
```

## Contract-first 规则

- 前后端不得各自发明字段、状态、错误码或分页结构。
- API 调整先修改 `openapi.yaml`，再在 `CONTRACT_CHANGELOG.md` 记录影响。
- 未合入契约的接口想法只能作为草案，不得作为另一端的实现依据。
- 前端应从 OpenAPI 生成或集中维护类型，不在页面中重复声明响应结构。
- 后端响应必须通过 OpenAPI 契约测试；不能用“前端兼容一下”替代契约修正。
- 并行开发期间，前端使用契约示例或 Mock Server，不等待后端完成全部逻辑。

## 推荐目录边界

后续创建代码时，建议保持以下所有权边界：

```text
frontend/       # 前端会话拥有
backend/        # 后端会话拥有
docs/api/       # 共享契约；修改需记录变更
docs/data/      # 数据库、文件存储、迁移与数据一致性规范
docs/development/
```

共享文档发生冲突时，以契约变更流程和当前项目状态台账处理。

## 契约校验

```bash
ruby scripts/validate_openapi.rb
```
