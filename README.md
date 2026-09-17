---
domain:
  - AutoML
tags:
  - data-analysis
  - fastapi
  - react
  - evidence
datasets:
  evaluation:
  test:
  train:
models:
license: apache-2.0
---

# AI Data Analyst Agent

面向 CSV、Excel 和 Parquet 的证据优先数据分析工作流系统。项目采用
React + FastAPI 前后端分离架构，以 OpenAPI 作为接口唯一事实源。

## 在线使用与最新进度

网站地址：[DataTrace 在线分析工作台](https://8.222.221.236.sslip.io/)。打开后可注册自己的
账号；注册成功会自动登录，项目与数据按账号隔离。密码须为 12-128 个字符且不能包含用户名。

截至 **2026-09-17**，阿里云新加坡轻量服务器上的小规模版本已正式上线，公网就绪检查正常，
自助注册和真实 AI Agent 已开启。最新完整验收包括：

- 新账号完成注册、自动登录、账号隔离、退出重登，并完成上传、质量扫描、模型训练、报告下载。
- 真实 DeepSeek Agent 完成证据解读、只读工具调用、分析规划、确认前阻断及确认后的真实建模执行；
  3 个轮次、6 次工具调用全部成功。
- 真实模型 Agent 五类固定数据集、50 个场景全部通过：任务、任务规则与硬规则均为 100%，
  P95 延迟 29.960 秒，未授权写操作为 0；完整基线与两例范围化复测链路保留在评测报告中。
- Agent 运行可按项目查看并只读回放，校验状态迁移、工具终态与资源引用，不会重复执行写操作。
- 最新候选版增加数据版本感知的结构化记忆、安全语义指标层、候选 Prompt/
  模型对比重放、受控工具执行检查点和脱敏 Bad Case 导出。
- 最新候选版后端 201 项、前端 37 项测试通过，后端覆盖率 83.32%，类型检查、
  OpenAPI 与生产构建通过。
- 服务器侧 500 请求、并发 8：0 失败，P95 211.184 ms，吞吐 54.740 req/s；该指标为轻量读取探针，
  不代表 8 个并发分析任务或大文件容量。
- Playwright 完成桌面与 390px 移动端注册、建项目、上传和 Agent 问答验收，无页面异常或 5xx。

当前为单机小规模试点（`CONDITIONAL GO`），使用 SQLite 和本机文件持久化，已配置每日
本机备份、健康巡检与服务自启动。异机备份、外部告警、自有域名和续费安排仍待补齐；跨境
访问延迟会受线路影响。LLM 使用 DeepSeek OpenAI-compatible API 与 `deepseek-flash`；模型不可用时，
核心分析、建模和报告仍可独立运行，证据回答会按策略降级。
详见[项目状态](docs/development/PROJECT_STATUS.md)、[线上验收记录](docs/quality/SMALL_TRAFFIC_ACCEPTANCE.md)和
[Agent 评测方法](docs/quality/AGENT_EVALUATION.md)。

## 目录导航

```text
.
├── backend/                 # FastAPI API、领域服务、持久化、Worker 和测试
├── frontend/                # React 页面、API Client、Mock 和组件测试
├── docs/
│   ├── api/                 # OpenAPI、对接规范和契约变更记录
│   ├── data/                # 数据持久化规范和数据库实现说明
│   ├── design/              # 产品界面概念图
│   ├── development/         # 技术决策、并行开发计划和会话指南
│   └── product/             # PRD/SRS 及最终渲染件
└── scripts/                 # 安装、契约校验和文档生成工具
```

第三方依赖和运行缓存不属于项目源码：

```text
backend/.venv/
frontend/node_modules/
backend/data/
frontend/dist/
```

## 开始开发

先阅读 [开发协作入口](docs/README.md)，再根据工作方向进入：

- [前端说明](frontend/README.md)
- [后端说明](backend/README.md)
- [当前项目状态与发布进程](docs/development/PROJECT_STATUS.md)
- [历史并行开发任务计划](docs/development/PARALLEL_DEVELOPMENT_PLAN.md)
- [OpenAPI 契约](docs/api/openapi.yaml)

安装后端依赖：

```bash
./scripts/install_deps.sh
```

启动后端：

```bash
cd backend
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

启动前端：

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev
```

## 质量检查

```bash
ruby scripts/validate_openapi.rb docs/api/openapi.yaml

cd backend
uv sync --frozen --extra dev
uv run ruff check app tests
uv run mypy app
uv run pytest --cov=app

cd ../frontend
pnpm typecheck
pnpm test
pnpm build
```

## 部署

项目提供生产 Compose 拓扑，迁移、FastAPI API、数据库队列 Worker 与 Nginx 前端
分别运行，并要求外部 PostgreSQL、私有 S3、HTTPS Cookie 和严格 Host 配置。

```bash
cp .env.deploy.example .env.deploy
docker compose --env-file .env.deploy up --build
ENV_FILE=.env.deploy ./scripts/production_gate.sh
```

详细步骤见 [部署指南](docs/deployment/DEPLOYMENT.md)；正式标签发布的摘要、SBOM、
provenance、签名和迁移/Smoke 记录要求见
[发布证据模板](docs/deployment/RELEASE_EVIDENCE.md)；可重复的上线小流量、真实工作流与恢复验收见
[小流量验收说明](docs/quality/SMALL_TRAFFIC_ACCEPTANCE.md)和
[历史本地候选验收报告（2026-09-09）](docs/quality/RELEASE_ACCEPTANCE_2026-09-09.md)。
阿里云轻量应用服务器的最低可运行单机方案见
[阿里云轻量部署说明](docs/deployment/ALIYUN_LIGHTWEIGHT.md)。

面向只能运行一个容器的平台仍可使用根目录 `Dockerfile`，但 API 与 Worker 无法独立
扩缩容和隔离故障，只建议用于受控试点。正式流量使用 Compose/编排平台的分离拓扑。

生产环境支持外部 PostgreSQL 与 S3 兼容对象存储。设置 PostgreSQL
`DATABASE_URL`、`STORAGE_BACKEND=s3` 和对应 `S3_*` 变量后，元数据、上传文件、
数据版本和导出产物不再依赖容器磁盘。`/api/v1/health/ready` 会同时检查两项依赖。
生产 Compose 中 Worker 与 API 使用独立进程、内存和 CPU 配额，长任务不会在 API
进程执行。数据库提交失败时，接入 Worker 会回滚已落到对象存储的最终对象。

上线前还必须完成环境侧 TLS/WAF、PITR、S3 版本控制、告警、负载测试、恢复演练与
隐私/法律签署；见 [生产就绪签署清单](docs/deployment/PRODUCTION_READINESS.md)。

## 真实分析与建模

建模运行不再只返回固定 Dummy 数值。分类任务会比较 Dummy、逻辑回归和
HistGradientBoosting；回归任务会比较 Dummy、Ridge 和
HistGradientBoostingRegressor。数值和类别预处理统一封装在 sklearn Pipeline
中，并且只在训练分区拟合。

模型选择仅使用训练分区交叉验证，随机、分层、时间和 Group 拆分均有独立实现；
保留集只进行最终一次评估。运行会保存目标驱动 EDA、统计检验及 BH 校正、候选
模型比较、Dummy 对照、混淆矩阵或残差摘要、置换重要性、限制说明和可下载的
joblib 模型包。核心计算完全不依赖大语言模型；已接入的 LLM 只允许根据现有
Artifact 组织叙述，不能生成或改写指标。

大模型扩展的 Gate L0～L4 已全部完成：后端提供可替换的 `LLMProvider`、无网络
`FakeLLMProvider`、OpenAI-compatible 适配器、严格结构化输出、Prompt 版本注册表和
安全故障映射。报告页可异步生成只读取已验证 Claim/Artifact 的 AI 证据解读；对话式
Assistant 支持项目内多轮问答、受约束分析规划、白名单工具、可编辑提案和显式确认后的真实
分析/清洗/报告执行。所有数字与引用均经过确定性校验，模型调用、工具调用、Token、确认和失败均可
审计，并支持不触发副作用的运行轨迹回放校验。该能力默认关闭；完成 Provider 配置并设置 `LLM_ENABLED=true` 后，报告解读和 Assistant
同时按系统能力开放。受控灰度已完成，但更广泛的生产放量仍受环境、合规和发布签署约束。
实施与验收记录见[大模型能力扩展计划](docs/development/LLM_EXTENSION_PLAN.md)和
[LLM 生产验收](docs/quality/LLM_PRODUCTION_ACCEPTANCE.md)。

## 目录维护规则

- 业务代码只放在 `frontend/` 或 `backend/`。
- 共享契约只放在 `docs/api/`，变更必须同步更新契约变更记录。
- 产品文档和设计资源统一放在 `docs/product/`、`docs/design/`。
- 可重复执行的工具放在 `scripts/`，不要在根目录堆放临时脚本。
- 构建产物、虚拟环境、依赖目录和缓存不得提交。

## ModelScope Clone

```bash
git clone https://www.modelscope.cn/studios/Ascano/ai-data-analyst-agent.git
```
