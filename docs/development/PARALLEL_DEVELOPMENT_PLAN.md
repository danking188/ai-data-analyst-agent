# 前后端并行开发任务计划

版本：1.0  
状态：可执行基线  
契约入口：[`../api/openapi.yaml`](../api/openapi.yaml)

## 1. 开发目标

前端和后端在两个独立会话中并行推进，以 OpenAPI 为唯一接口事实源。第一阶段交付一个可运行的纵向切片：

```text
创建项目
→ 上传 CSV/XLSX/Parquet
→ 查看 Job 进度
→ 查看数据版本与预览
→ 查看/修改 Schema
→ 启动质量扫描
→ 查看质量问题
```

完成该切片后，再按清洗、EDA/建模、证据与导出的顺序扩展。

## 2. 工作区与所有权

建议使用两个分支或 Git worktree：

| 会话 | 建议分支 | 主要所有权 |
|---|---|---|
| 前端 | `codex/frontend-mvp` | `frontend/**` |
| 后端 | `codex/backend-mvp` | `backend/**` |
| 共享契约 | 通过单独小提交修改 | `docs/api/**` |

规则：

- 前端会话不修改 `backend/**`。
- 后端会话不修改 `frontend/**`。
- 两端都可提出契约变更，但必须单独提交 `docs/api/openapi.yaml` 与 `CONTRACT_CHANGELOG.md`。
- 契约变更未确认前，代码只能保留在本地草案，不得要求另一端适配。
- 每完成一个可联调任务，更新本文件对应状态。

状态标记：

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 完成
- `[!]` 阻塞；后面必须写明原因

## 3. 共享任务

| ID | 状态 | 任务 | 产物 | 完成条件 |
|---|---|---|---|---|
| SH-001 | [x] | 建立 OpenAPI 1.0 基线 | `docs/api/openapi.yaml` | YAML 可解析；引用有效 |
| SH-002 | [x] | 建立 API 通用规范 | `API_INTEGRATION_STANDARD.md` | 分页、错误、异步、上传、幂等规则明确 |
| SH-003 | [x] | 确认技术栈和目录结构 | `TECH_STACK_DECISION.md` | 前后端技术栈、目录、端口与环境变量确定 |
| SH-004 | [x] | 配置契约校验 | `scripts/validate_openapi.rb` | OpenAPI YAML、引用、operationId 和路径参数可校验 |
| SH-005 | [x] | 生成前端 API 类型 | `frontend/src/api/generated/**` | 与 OpenAPI 一致且类型检查通过 |
| SH-006 | [x] | 建立 Mock Server | 前端开发命令/Mock 配置 | 无后端时可覆盖纵向切片 |
| SH-007 | [x] | 建立后端契约测试 | `backend/tests/contract/**` | 关键响应与状态码符合 OpenAPI |
| SH-008 | [x] | 冻结 MVP 容量和认证决策 | `TECH_STACK_DECISION.md` | 500 MiB、开发 Bearer token、生产 JWT |
| SH-009 | [x] | 建立数据持久化与数据库规范 | `../data/DATA_PERSISTENCE_STANDARD.md` | 表、关系、状态机、文件存储、迁移、索引与测试要求明确 |

## 4. 前端任务轨道

### FE-0 工程基础

| ID | 状态 | 依赖 | 任务 | 完成条件 |
|---|---|---|---|---|
| FE-001 | [x] | SH-003 | 创建前端工程和环境配置 | 本地可启动；API Base URL 可配置 |
| FE-002 | [x] | FE-001, SH-005 | 建立统一 API Client | 自动注入 token、request_id 日志、错误解析 |
| FE-003 | [x] | FE-002 | 实现 Job 轮询 Hook/Store | 支持终态、退避、页面后台降频和取消 |
| FE-004 | [x] | FE-001 | 建立全局错误与通知组件 | 按错误码呈现；不展示堆栈 |
| FE-005 | [x] | FE-001 | 建立项目/数据版本上下文 | 页面持续显示 project_id 与 version_id |

### FE-1 首个纵向切片

| ID | 状态 | 依赖 | 任务 | 对应 operationId | 完成条件 |
|---|---|---|---|---|---|
| FE-101 | [x] | FE-002 | 项目列表与创建 | `listProjects`, `createProject` | loading/empty/error/success 完整 |
| FE-102 | [x] | FE-003, FE-005 | 文件上传 | `uploadDataset`, `getJob` | 进度、超限、格式错误和解析失败可见 |
| FE-103 | [x] | FE-102 | 数据集与版本链 | `listDatasets`, `listDatasetVersions` | 当前版本和父版本关系清晰 |
| FE-104 | [x] | FE-103 | 数据分页预览 | `previewDatasetVersion` | cursor 正确；敏感列有掩码提示 |
| FE-105 | [x] | FE-103 | Schema 审阅与编辑 | `getDatasetSchema`, `updateDatasetSchema` | 低置信度筛选、revision 冲突处理 |
| FE-106 | [x] | FE-103, FE-003 | 质量扫描与问题列表 | `createQualityScan`, `listQualityIssues` | Job 完成后刷新；严重度和状态筛选 |
| FE-107 | [x] | FE-106 | 质量问题处置 | `updateQualityIssue` | 忽略需原因；冲突时刷新 |

### FE-2 清洗与版本

| ID | 状态 | 依赖 | 任务 | 对应 operationId | 完成条件 |
|---|---|---|---|---|---|
| FE-201 | [x] | FE-107 | 清洗计划编辑器 | `createCleaningPlan`, `updateCleaningPlan` | 只使用白名单操作与契约字段 |
| FE-202 | [x] | FE-201, FE-003 | 清洗影响预览 | `previewCleaningPlan` | 显示影响行数、风险和预览 Artifact |
| FE-203 | [x] | FE-202 | 审批与拒绝 | `decideCleaningPlan` | 高风险逐项确认；记录理由 |
| FE-204 | [x] | FE-203, FE-003 | 执行、结果版本与回滚 | `executeCleaningPlan`, `activateDatasetVersion` | 新版本出现；历史运行绑定不变 |
| FE-205 | [x] | FE-204 | 版本比较 | `compareDatasetVersions` | 不可比项有原因说明 |

### FE-3 分析、证据与报告

| ID | 状态 | 依赖 | 任务 | 对应 operationId | 完成条件 |
|---|---|---|---|---|---|
| FE-301 | [x] | FE-105 | AnalysisSpec 向导 | `createAnalysisSpec`, `updateAnalysisSpec`, `confirmAnalysisSpec` | 预测时点、拆分和指标可确认 |
| FE-302 | [x] | FE-301, FE-003 | 运行进度页面 | `createRun`, `getRun`, `cancelRun` | 步骤状态、取消、失败定位完整 |
| FE-303 | [x] | FE-302 | Artifact 查看器 | `listArtifacts`, `getArtifact` | 图表/表格/指标按类型渲染 |
| FE-304 | [x] | FE-303 | Claim 与证据抽屉 | `listClaims`, `getClaim` | 两次操作内到达证据；限制条件可见 |
| FE-305 | [x] | FE-304, FE-003 | 报告与导出 | `createReportExport`, `createArtifactDownload` | 导出任务、过期下载和错误状态完整 |

## 5. 后端任务轨道

### BE-0 工程基础

| ID | 状态 | 依赖 | 任务 | 完成条件 |
|---|---|---|---|---|
| BE-001 | [x] | SH-003 | 创建后端工程、配置和健康检查 | `/health`、`/system/capabilities` 符合契约 |
| BE-002 | [x] | BE-001 | 统一错误与 request_id 中间件 | 所有异常输出 `ErrorResponse` |
| BE-003 | [x] | BE-001 | 数据库、迁移与 Repository 基础 | 项目、数据集、版本、Job 可持久化；符合数据持久化规范 |
| BE-004 | [x] | BE-001 | 项目权限隔离 | 跨项目访问测试通过 |
| BE-005 | [x] | BE-003 | 幂等键与 revision/If-Match | 重复请求和版本冲突符合规范 |
| BE-006 | [x] | BE-003 | Job 队列与状态机 | 进程重启后无遗留假 running |
| BE-007 | [x] | SH-007 | 契约测试基础 | 至少覆盖健康、错误、分页和 Job |

### BE-1 首个纵向切片

| ID | 状态 | 依赖 | 任务 | 对应 operationId | 完成条件 |
|---|---|---|---|---|---|
| BE-101 | [x] | BE-002~005 | 项目 CRUD/归档 | `listProjects`, `createProject`, `getProject`, `updateProject`, `archiveProject` | 权限、分页、revision 测试通过 |
| BE-102 | [x] | BE-006 | 文件上传与安全校验 | `uploadDataset` | 哈希、大小、扩展名与内容校验完成 |
| BE-103 | [x] | BE-102 | CSV/Excel/Parquet 解析 | Job + DatasetVersion | 三种格式解析、Excel 多工作表约束、Parquet 标准化与失败隔离均已完成 |
| BE-104 | [x] | BE-103 | 数据集、版本链和预览 | `listDatasets`, `listDatasetVersions`, `previewDatasetVersion` | 版本状态、签名 cursor、列裁剪和敏感字段脱敏已完成 |
| BE-105 | [x] | BE-103 | 字段画像与 Schema 推断 | `getDatasetSchema`, `updateDatasetSchema` | 字段画像、低置信度统计、用户覆盖持久化与 revision 冲突保护已完成 |
| BE-106 | [x] | BE-105, BE-006 | 质量扫描引擎 | `createQualityScan`, `listQualityIssues` | 六类确定性规则、异步 Job、结构化 metrics、筛选与强制重扫已完成 |
| BE-107 | [x] | BE-106 | 质量问题处置 | `updateQualityIssue` | 状态约束、忽略理由、revision 冲突、用户决定与审计事件已完成 |

### BE-2 清洗与版本

| ID | 状态 | 依赖 | 任务 | 对应 operationId | 完成条件 |
|---|---|---|---|---|---|
| BE-201 | [x] | BE-107 | 清洗操作注册表与计划 CRUD | `createCleaningPlan`, `updateCleaningPlan` | 七类白名单操作、参数 Schema、字段和质量问题引用校验已完成 |
| BE-202 | [x] | BE-201, BE-006 | 确定性预览 | `previewCleaningPlan` | 预览与执行复用纯函数；结果持久化为脱敏 Artifact |
| BE-203 | [x] | BE-202 | 审批状态机与审计 | `decideCleaningPlan` | 预览前不可审批；拒绝原因、用户决定和审计事件已完成 |
| BE-204 | [x] | BE-203, BE-006 | 原子执行与不变量 | `executeCleaningPlan` | 生成 cleaned 子版本；空结果失败且不激活；成功原子提交并切换当前版本 |
| BE-205 | [x] | BE-204 | 版本激活与比较 | `activateDatasetVersion`, `compareDatasetVersions` | 历史版本激活、同源校验、异步差异计算、脱敏样例和比较 Artifact 已完成 |

### BE-3 分析、证据与报告

| ID | 状态 | 依赖 | 任务 | 对应 operationId | 完成条件 |
|---|---|---|---|---|---|
| BE-301 | [x] | BE-105 | AnalysisSpec 修订与校验 | AnalysisSpec operations | 不可变修订、幂等确认、字段/任务/拆分/指标兼容校验及审计已完成 |
| BE-302 | [x] | BE-301, BE-006 | AnalysisRun 编排与 Tool Registry | Run operations | 运行/步骤状态机、异步 Job、取消、审计及工具名称+版本白名单已完成 |
| BE-303 | [x] | BE-302 | 自动 EDA 与 Chart Planner | Artifact operations | 运行自动生成 metric/table/chart Artifact；图表绑定输入版本和参数；Artifact 查询接口已完成 |
| BE-304 | [x] | BE-302 | Baseline Pipeline | Run/Artifact operations | 建模任务生成 Dummy Baseline model/metric Artifact；拆分先于拟合；仅使用训练集拟合 |
| BE-305 | [x] | BE-303~304 | Artifact 与 Claim Validator | Evidence operations | Artifact/Claim 查询接口完成；运行自动生成证据结论；含数字结论无证据不能 passed |
| BE-306 | [x] | BE-305, BE-006 | HTML/Notebook/Data/Manifest 导出 | Report operations | HTML/Notebook/Data/Manifest 异步导出完成；file Artifact 可下载；Manifest 含校验信息且不含密钥 |
| BE-307 | [x] | BE-302 | 沙箱和资源限制 | 执行器内部能力 | 工具白名单、DATA_ROOT 路径限制、代码/网络参数拒绝、AST 安全表达式测试通过 |

## 6. 可并行关系

```text
SH-003 技术栈确认
├── FE-001 → FE-002 → FE-101
├── FE-001 → Mock → FE-102/103/104/105/106
└── BE-001 → BE-002/003/004
                  └── BE-006

契约稳定后：
FE-101～107 可以使用 Mock 连续开发
BE-101～107 可以独立用契约测试开发
两端只在纵向切片门禁处汇合
```

## 7. 联调门禁

### Gate 1：基础协议

- `/health` 和 `/system/capabilities` 可访问。
- 鉴权策略确定。
- `ErrorResponse`、分页和 request_id 一致。
- 前端 API Client 与后端契约测试通过。

### Gate 2：上传纵向切片

- 创建项目、上传文件、Job 轮询、版本链、预览全部贯通。
- 文件过大、格式不支持、解析失败、取消任务均验证。
- 刷新页面后 Job 和版本状态不丢失。

### Gate 3：Schema 与质量

- 低置信度字段、Schema 修改、revision 冲突验证。
- 质量扫描和问题筛选/处置贯通。
- 不存在字段与跨项目访问被后端阻断。

### Gate 4：清洗与版本

- 预览、批准、执行、新版本、回滚和比较贯通。
- 未批准计划不可执行。
- 失败执行不生成可用版本。

### Gate 5：分析与交付

- AnalysisSpec、Run、Artifact、Claim 和导出贯通。
- 正式报告不包含验证失败 Claim。
- Notebook/Manifest 重跑与完整性检查通过。

## 8. 每日同步模板

两个会话结束前都应输出并写入任务状态：

```text
今日完成：
- [任务 ID] 结果

契约变化：
- 无 / 变更编号与文件

待另一端确认：
- operationId：
- 请求/响应问题：
- 期望确认时间：

阻塞：
- [任务 ID] 原因与解除条件

下一步：
- [任务 ID]
```

## 9. 契约变更请求模板

```text
变更标题：
提出方：前端 / 后端
相关 operationId：
当前问题：
建议修改：
兼容性：Patch / Minor / Breaking
前端影响：
后端影响：
迁移方案：
```

## 10. 第一轮推荐任务

前端会话：

```text
FE-001 → FE-002 → FE-003 → FE-101 → FE-102
```

后端会话：

```text
BE-001 → BE-002 → BE-003 → BE-005 → BE-006 → BE-101
```

第一轮结束后执行 Gate 1，再进入上传纵向切片。

## 11. 生产化与部署阶段

| ID | 状态 | 任务 | 完成条件 |
|---|---|---|---|
| PROD-001 | [x] | 移除分析、模型、报告和概览中的静态业务数据 | 页面内容来自 DatasetSchema、Run、Artifact 和 Claim |
| PROD-002 | [x] | 登录会话与受保护下载 | HttpOnly JWT Cookie 登录；有时效签名下载可用 |
| PROD-003 | [x] | 单容器生产镜像 | 根 Dockerfile 在 7860 同时提供前端与 API |
| PROD-004 | [x] | 真实数据端到端验收 | CSV 上传、AnalysisSpec、Run、Artifact、Claim、HTML 下载贯通 |
| PROD-005 | [x] | 桌面和移动端浏览器验收 | 无控制台错误；390px 无横向溢出；抽屉不遮挡正文 |
| PROD-006 | [x] | 发布 ModelScope 创空间 | Docker 创空间构建并运行；健康检查、登录和真实 CSV 全流程 Smoke 验收通过 |
| PROD-007 | [x] | 持久化账号与开放注册 | 用户表迁移、Scrypt 密码哈希、失败锁定、账号隔离和注册 UI 验收通过 |
| PROD-008 | [~] | 外部 PostgreSQL 与对象存储 | 适配器、就绪检查和本地测试完成；等待云端连接凭据执行跨部署验收 |
