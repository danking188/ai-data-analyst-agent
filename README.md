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
- [并行开发任务计划](docs/development/PARALLEL_DEVELOPMENT_PLAN.md)
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
.venv/bin/ruff check app tests
.venv/bin/mypy app
.venv/bin/pytest

cd ../frontend
pnpm typecheck
pnpm test
pnpm build
```

## 部署

项目提供 Docker Compose 部署基线，包含 FastAPI 后端、Nginx 前端静态服务、
API 反向代理、健康检查和 smoke 脚本。

```bash
cp .env.deploy.example .env.deploy
docker compose --env-file .env.deploy up --build
./scripts/deploy_smoke.sh
```

详细步骤见 [部署指南](docs/deployment/DEPLOYMENT.md)。

面向单容器云平台时使用根目录 `Dockerfile`。它会在同一个 `7860` 端口提供
登录页、React 前端、FastAPI API 和报告下载，并将运行数据写入
`/mnt/workspace/data`。生产环境必须配置 `LOGIN_USERNAME`、`LOGIN_PASSWORD`
和不少于 32 个字符的 `JWT_SECRET`；前端不再包含开发 token。
设置 `REGISTRATION_ENABLED=true` 后，注册账号以 Scrypt 哈希写入持久化数据库，
不同账号的项目和数据按项目成员关系隔离。

生产环境支持外部 PostgreSQL 与 S3 兼容对象存储。设置 PostgreSQL
`DATABASE_URL`、`STORAGE_BACKEND=s3` 和对应 `S3_*` 变量后，元数据、上传文件、
数据版本和导出产物不再依赖容器磁盘。`/api/v1/health/ready` 会同时检查两项依赖。
生产镜像还会监督独立的数据库队列 Worker，避免长任务占用 API 请求进程。

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
