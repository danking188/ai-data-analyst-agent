# Database design

版本：1.0  
数据库：SQLite（MVP）  
ORM：SQLAlchemy 2  
迁移：Alembic

## 1. 设计原则

- SQLite 只存元数据、状态、审计和 Artifact 索引；原始/清洗数据使用只读文件与 Parquet。
- `DatasetVersion`、已完成的 `AnalysisRun` 和 ready `Artifact` 作为不可变记录使用。
- 数据版本通过 `parent_version_id` 形成分支链，回滚只改变当前指针，不删除历史。
- 所有项目资源都带 `project_id`，Repository 查询必须显式限定项目。
- 可编辑资源使用 `revision` 乐观锁；API 使用 `If-Match`。
- 创建型操作使用 `idempotency_keys`，默认保留 24 小时。
- Job 使用租约、心跳与终态；服务启动时将过期 running/cancelling Job 标记为失败。
- 所有时间以 UTC 写入，读取时恢复为 timezone-aware `datetime`。
- SQLite 连接强制启用 foreign keys、WAL、5 秒 busy timeout。

## 2. 表分组

### 基础与权限

| 表 | 用途 |
|---|---|
| `projects` | 项目元数据、revision、当前数据版本指针 |
| `project_members` | owner/editor/viewer 项目权限 |
| `audit_logs` | 关键写操作、拒绝和失败审计 |
| `idempotency_keys` | 请求哈希、响应快照和资源/Job 绑定 |

### 数据与质量

| 表 | 用途 |
|---|---|
| `datasets` | 逻辑数据集及当前版本指针 |
| `dataset_versions` | 不可变数据快照、哈希、存储键和父版本 |
| `column_schemas` | 物理类型、语义类型、分析角色、画像和用户覆盖 |
| `quality_issues` | 确定性质量事实、指标、严重度和处置状态 |

### 清洗

| 表 | 用途 |
|---|---|
| `cleaning_plans` | 来源版本、审批、预览 Artifact 和结果版本 |
| `cleaning_operations` | 有序白名单操作与参数 |
| `user_decisions` | 清洗、Schema、风险等显式用户决定 |

### 分析与证据

| 表 | 用途 |
|---|---|
| `analysis_specs` | 以 `spec_revision_id` 保存不可变修订 |
| `analysis_runs` | 一次执行的版本、环境、状态和随机种子 |
| `analysis_steps` | 有序工具步骤、参数和错误 |
| `artifacts` | 真实代码结果、校验和和存储索引 |
| `claims` | 结论文本、级别、限制和发布状态 |
| `claim_evidence` | Claim 与 Artifact 多对多证据关系 |
| `validation_results` | 独立验证器的版本化结果 |
| `conversation_summaries` | 最小上下文的长期结构化摘要 |

### 异步执行

| 表 | 用途 |
|---|---|
| `jobs` | 队列状态、进度、租约、心跳、结果资源和错误 |

## 3. 当前指针为什么不使用外键

`projects.current_dataset_version_id` 和 `datasets.current_version_id` 是便捷查询指针，刻意不建立数据库外键。否则会与 `dataset_versions → datasets/projects` 形成 DDL 环，影响 SQLite 迁移排序。

Repository 的 `activate_version()` 在同一事务中验证：

1. 项目、数据集、版本属于同一作用域；
2. 目标版本状态为 `ready`；
3. 同时更新 Dataset 和 Project 指针；
4. 提升 Project revision。

真正的数据谱系完整性仍由 `dataset_versions.dataset_id/project_id/parent_version_id` 外键保障。

## 4. 事务边界

应用服务应使用 `UnitOfWork`：

```python
session = database.session()
with UnitOfWork(session) as uow:
    project = uow.projects.create(...)
    uow.audit.append(...)
```

- 上下文正常退出时 commit。
- 发生异常时 rollback。
- Repository 可以 flush 以取得约束错误，但不自行 commit。
- 文件写入采用“临时文件 → 数据库事务 → 原子重命名/补偿”策略，不能把半成品标记为 ready。

## 5. 迁移规则

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "describe change"
.venv/bin/alembic check
```

约束：

- 应用启动不调用 `metadata.create_all()`。
- 历史迁移合入主分支后不得改写。
- 自动生成迁移必须人工检查 upgrade、downgrade、外键和索引。
- 每次变更验证空库升级、已有库升级、downgrade/upgrade 往返。

## 6. Repository 接口

现有 Repository：

- `ProjectRepository`：成员隔离、分页、原子 revision 更新、归档。
- `DatasetRepository`：数据集、版本创建、ready/failed 终态、激活和版本分页。
- `JobRepository`：创建、项目/成员查询、租约、心跳、状态迁移、过期恢复。
- `IdempotencyRepository`：请求占位、重放、冲突检测和响应快照。
- `AuditRepository`：只追加审计记录。

API/service 层不得直接构造任意 SQL 绕过项目作用域和状态验证。

## 7. 验证命令

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest
DATABASE_URL=sqlite:////tmp/agent.db .venv/bin/alembic upgrade head
DATABASE_URL=sqlite:////tmp/agent.db .venv/bin/alembic check
```

