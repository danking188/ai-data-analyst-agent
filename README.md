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
[发布证据模板](docs/deployment/RELEASE_EVIDENCE.md)。

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
joblib 模型包。核心计算完全不依赖大语言模型；未来接入 LLM 时只允许根据现有
Artifact 组织叙述，不能生成或改写指标。

大模型扩展的 Gate L0 和 Gate L1 已经完成：后端提供可替换的 `LLMProvider`、无网络
`FakeLLMProvider`、OpenAI-compatible 适配器、严格结构化输出、Prompt 版本注册表和
安全故障映射。报告页可异步生成只读取已验证 Claim/Artifact 的 AI 证据解读，所有数字和
引用均经过确定性校验，并可进入 HTML、Notebook 和 Manifest。该能力默认关闭；配置模型后
设置 `LLM_ENABLED=true` 只开放报告解读，对话式 Assistant 仍等待 Gate L2。实施进度见
[大模型能力扩展计划](docs/development/LLM_EXTENSION_PLAN.md)。

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
