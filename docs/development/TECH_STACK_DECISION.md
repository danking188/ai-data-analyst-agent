# 技术栈与本地开发基线

决策编号：ADR-001  
状态：已采用，后续可通过 ADR 变更  
日期：2026-07-09

## 1. 决策

为支持两个独立会话真正并行开发，MVP 采用前后端分离结构：

### 前端

- React 19
- TypeScript
- Vite
- React Router
- TanStack Query：服务端状态、缓存与 Job 轮询
- Zod：仅用于前端运行时边界校验，不重复定义 OpenAPI 模型
- Plotly.js：图表展示
- Vitest + React Testing Library
- Playwright：端到端联调

### 后端

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2 + Alembic
- SQLite：MVP 元数据
- pandas + PyArrow
- DuckDB：P1 查询增强；不作为首轮阻塞依赖
- scikit-learn、SciPy、statsmodels、Plotly
- Jinja2、nbformat
- Pytest

### 契约与开发工具

- OpenAPI 3.1
- 前端类型：从 `docs/api/openapi.yaml` 生成
- 后端路由与响应模型：对照同一 OpenAPI 进行契约测试
- 本地 Mock：OpenAPI Mock Server 或 MSW

## 2. 为什么不继续使用 Streamlit 作为主 UI

原始产品设计推荐 Streamlit，适合快速 Demo，但当目标是“前端、后端在两个会话中同步开发”时，Streamlit 会把页面状态、服务调用和 Python 业务逻辑重新耦合在一起。React + FastAPI 更适合：

- 通过 OpenAPI 提前冻结接口；
- 前端使用 Mock 独立推进；
- 后端使用契约测试独立推进；
- 明确控制异步任务、上传、权限和错误状态；
- 后续扩展更复杂的证据查看器和建模交互。

如果目标重新变为短期单机 Demo，可另立 ADR 切回 Streamlit，但不能在同一阶段同时维护两套主 UI。

## 3. 建议目录

```text
frontend/
├── src/
│   ├── api/
│   │   ├── generated/
│   │   ├── client.ts
│   │   └── errors.ts
│   ├── features/
│   ├── routes/
│   ├── components/
│   └── test/
├── package.json
└── vite.config.ts

backend/
├── app/
│   ├── api/
│   ├── domain/
│   ├── services/
│   ├── repositories/
│   ├── workers/
│   └── main.py
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── contract/
└── pyproject.toml
```

## 4. 本地端口与环境变量

| 服务 | 地址 |
|---|---|
| 前端 | `http://localhost:5173` |
| 后端 API | `http://localhost:8000/api/v1` |
| 后端 OpenAPI UI | `http://localhost:8000/docs` |

前端：

```text
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_API_MODE=mock|real
```

后端：

```text
APP_ENV=development
API_PREFIX=/api/v1
DATABASE_URL=sqlite:///./data/app.db
DATA_ROOT=./data
MAX_UPLOAD_BYTES=524288000
AUTH_MODE=dev_token|jwt
DEV_AUTH_TOKEN=仅本地使用，不提交仓库
```

## 5. 认证与容量基线

- 开发环境：Bearer dev token，后端仍执行项目权限校验；不使用“完全跳过鉴权”的隐藏分支。
- 非开发环境：Bearer JWT，具体身份提供商可后置决定。
- 单文件默认上限：500 MiB，即 `524288000` 字节。
- 支持格式：CSV、XLS、XLSX、Parquet。
- 最终部署可调低上限，并通过 `/system/capabilities` 告知前端。

## 6. 决策约束

- 前端不得直接读取 SQLite、Parquet 或本地文件路径。
- 后端不得把页面展示逻辑写入分析服务。
- 两端共享的业务枚举必须来自 OpenAPI。
- 修改技术栈、认证模式或 API 主版本时新增 ADR，不直接改写本文件历史结论。

