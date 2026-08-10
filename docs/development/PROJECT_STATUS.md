# DataTrace 项目状态与发布进程

最后更新：2026-08-11
当前阶段：候选发布（Repository Release Candidate）
总体结论：仓库内高优先级安全与发布工程已完成；生产环境验收尚未签署，当前不可正式放量。

版本控制快照：`master`。本文件所在提交即为候选发布源码；是否可放量以该不可变 SHA 的 CI/安全门禁与生产环境签署为准。

## 状态标记

- `[ ]` 未开始
- `[~]` 进行中
- `[x]` 已完成并有验证证据
- `[!]` 需要外部环境、负责人或审批

每完成一个工作项，必须同时更新本文件中的状态、验证证据和末尾变更记录。

## 当前执行顺序

| 顺序 | ID | 状态 | 工作项 | 完成证据 |
| --- | --- | --- | --- | --- |
| 1 | REL-001 | [x] | 生产认证、CSRF、Host、Cookie 和安全响应头加固 | 后端安全/契约测试通过 |
| 2 | REL-002 | [x] | API、迁移、Worker 分离及资源限制 | Compose 配置校验通过 |
| 3 | REL-003 | [x] | 存储写入补偿、过期任务恢复和结构化日志 | 单元/集成测试通过 |
| 4 | REL-004 | [x] | 项目/版本切换、游标分页、版本比较和受保护下载闭环 | 前端单测与真实浏览器 Smoke 通过 |
| 5 | REL-005 | [x] | 锁文件、CI、依赖审计、容器扫描和 Dependabot | CI/Security 工作流已配置；本地审计无已知漏洞 |
| 6 | REL-006 | [x] | 备份、恢复、S3 版本控制及离线 LLM 发布门禁 | 脚本语法与 LLM 控制套件通过 |
| 7 | CLEAN-001 | [x] | 清理无引用代码、过时开发提示和本地生成产物 | 引用扫描通过；可再生目录已删除；CI 卫生门禁已建立 |
| 8 | REL-007 | [x] | 补齐环境样例、三类镜像扫描及清理后的全量回归 | 代码、测试、契约、审计、构建、Compose、脚本和卫生门禁通过 |
| 9 | REL-008 | [x] | 镜像运行时、供应链和发布流程加固 | 三镜像非 root；SBOM/provenance；Scout 0 Critical/High；容器 Smoke 通过 |
| 10 | ENV-001 | [!] | 生产环境基础设施及业务签署 | `PRODUCTION_READINESS.md` 全部签署 |

## 已验证的仓库基线

| 范围 | 当前证据 |
| --- | --- |
| 后端质量 | Ruff、Mypy 通过；148 个测试通过；覆盖率 82.61% |
| 前端质量 | TypeScript 通过；26 个测试通过；生产构建通过 |
| API 契约 | 50 个路径、63 个操作、398 个引用通过；生成类型与 OpenAPI 一致 |
| 浏览器 | 桌面和 390px 手机视口通过；项目切换、分页、版本比较正常；0 error / 0 warning |
| 依赖安全 | `pip-audit` 与 `pnpm audit` 无已知漏洞 |
| LLM 离线门禁 | 50 个评估场景及确定性引用、隔离、确认、配额和红队测试通过 |
| 部署配置 | Compose 渲染通过；后端、前端、试点三类候选镜像已成功构建 |
| 镜像供应链 | 构建附带 SBOM/provenance；三镜像 Docker Scout 均为 0 Critical / 0 High |
| 容器运行时 | 后端/试点 UID 999，前端 UID 101；前端 HTTP 200 + 安全头；试点迁移/Worker/API/readiness 通过 |

最后一次仓库回归（2026-08-10）：后端 148 个测试、82.61% 覆盖率，前端 26 个测试，
OpenAPI 50/63/398 校验、生成类型一致性、LLM 离线门禁、Python/前端生产依赖审计、
生产构建、Compose 渲染、Workflow YAML、Shell 语法和仓库卫生检查全部通过。

最后一次镜像回归（2026-08-11）：三类 `linux/arm64` 镜像均成功构建并附带
SBOM/provenance；移除运行时 `uv/uvx` 后，后端和试点包数从 662 降为 154；
前端升级到 `nginx:1.30.4-alpine-slim` 后从 68 包降为 21 包。三镜像无可修复
Critical/High 漏洞，非 root 运行、前端 HTTP/安全头和试点 fail-closed/readiness 验证通过。

已知非阻断技术债：本机 Python 3.14 测试环境会从 FastAPI/Starlette 的 TestClient
兼容层发出一条 `httpx` 弃用警告；项目自身已移除 `RefResolver` 弃用调用，CI 仍以
Python 3.12 为目标。后续依赖升级时应迁移至上游推荐的 TestClient 依赖。

## 生产环境待签署

以下工作不能由代码仓库代替生产环境证明；在全部完成前保持 No-Go：

| ID | 状态 | 事项 | 责任角色 | 必需证据 |
| --- | --- | --- | --- | --- |
| ENV-101 | [!] | DNS、TLS、HTTPS 跳转、WAF、限流和 DDoS 防护 | Platform/Security | 公网探测与 TLS/WAF 报告 |
| ENV-102 | [!] | Secret Manager、密钥轮换和最小权限 | Security | 配置引用与轮换演练记录 |
| ENV-103 | [!] | PostgreSQL TLS、PITR、容量及恢复演练 | DBA/QA | 隔离数据库恢复和 Smoke 证据 |
| ENV-104 | [!] | 私有对象存储、加密、版本控制和生命周期 | Platform | 版本控制检查与对象恢复证据 |
| ENV-105 | [!] | 集中日志、指标、告警接收人和合成探针 | SRE | 告警触发/恢复记录 |
| ENV-106 | [!] | 100 MiB 代表文件、Worker 并发和长稳测试 | QA/SRE | 负载报告、资源曲线和 SLO 结论 |
| ENV-107 | [!] | 数据分级、保留/删除、隐私及供应商合规 | Legal/Security | 已批准策略或 DPA |
| ENV-108 | [!] | 正式账号模式和 LLM Canary/回滚 | Product/AI/Security | 决策记录、Canary 与回滚记录 |
| ENV-109 | [!] | 镜像构建、扫描、摘要和迁移演练 | Release Manager | 本地预检已通过；待 CI SHA、签名镜像摘要、SBOM/provenance 和目标环境发布记录 |

详细的 Go/No-Go 条件和负责人签署矩阵见
[`../deployment/PRODUCTION_READINESS.md`](../deployment/PRODUCTION_READINESS.md)。

## 本轮清理判定

### 删除

- 无任何 import 或路由引用的 `WorkflowPlaceholder.tsx`。
- 仅适用于早期双会话开发方式的前后端 Session Prompt。
- 依赖开放注册、已被现行部署 Smoke 与备份恢复流程替代的 `persistence_smoke.sh`。
- 可再生的覆盖率、类型检查、测试、Python 字节码、前端构建和浏览器临时产物。

### 保留

- 两份根目录 CSV：用户数据，不作为遗留物处理。
- `.env.production.local`：可能包含本地私密配置，保持忽略且不读取、不删除。
- `backend/.venv` 与 `frontend/node_modules`：当前验证所需依赖环境。
- 根 `Dockerfile` 与 `app.production`：仍是受控单容器试点入口。
- PRD、PDF、逐页渲染图和界面概念图：有明确文档或设计用途。

## 变更记录

- 2026-08-10：建立当前项目状态台账；仓库基线记录完成。
- 2026-08-10：删除无引用占位组件、早期 Session Prompt、旧持久化 Smoke，以及本地缓存/构建产物；建立 CI 仓库卫生门禁；开始清理后回归。
- 2026-08-10：修复干净克隆缺少前后端 `.env.example` 的问题；安全工作流覆盖 API、前端 Nginx 和单容器试点三个镜像；补充单容器试点的 fail-closed 配置说明。
- 2026-08-10：移除契约测试对已弃用 `jsonschema.RefResolver` 的依赖，改用 OpenAPI 3.1 对应的 Draft 2020-12 校验器。
- 2026-08-10：修正 Python 审计流程，不再尝试构建本地可编辑项目或临时升级 pip；当前 Python 与前端生产依赖复审均无已知漏洞。
- 2026-08-10：清理后全量回归完成；REL-007 关闭；测试生成的缓存和构建产物再次清除，仓库进入候选发布状态。
- 2026-08-11：三类候选镜像完成本地构建、SBOM/provenance、非 root 和真实容器 Smoke 验证。
- 2026-08-11：根据镜像扫描移除运行时 `uv/uvx`，将前端基础镜像升级为 Nginx 1.30.4 Alpine Slim；三镜像复扫均为 0 Critical / 0 High。
- 2026-08-11：新增标签发布流程，只在 CI/安全门禁通过后发布多架构镜像，附带 SBOM/provenance、Sigstore 签名和发布证据清单。
