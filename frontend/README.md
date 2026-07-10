# DataTrace 前端

AI Data Analyst Agent 的 React 19 + TypeScript + Vite 前端。

## 当前实现范围

- FE-001：Vite/TypeScript 工程与环境配置；
- FE-002：统一 API Client、Bearer token、错误解析、幂等键；
- FE-003：Job 轮询、刷新恢复、取消与终态处理；
- FE-004：统一错误、空状态、加载状态和操作反馈组件；
- FE-005：项目、数据集和数据版本上下文；
- FE-101：项目查询与创建；
- FE-102：CSV/XLS/XLSX/Parquet 上传、大小/格式校验和 Job 进度；
- FE-103：数据集与版本链；
- FE-104：数据预览、敏感字段掩码和 cursor 继续加载入口；
- FE-105：Schema 审阅、类型/角色修改、revision 更新；
- FE-106：质量扫描、Job 进度和问题列表；
- FE-107：质量问题接受/忽略及原因记录。
- FE-201～FE-205：清洗计划编辑、确定性预览、审批、执行、版本激活/回滚与比较；
- FE-301～FE-302：AnalysisSpec 向导、确认运行、步骤进度、取消与失败定位；
- FE-303：Metric、Chart、Table、Log Artifact 分类查看；
- FE-304：Claim 结论、局限条件与 Claim → Artifact → Run → Dataset 证据链；
- FE-305：HTML、Notebook、清洗数据和 Manifest 异步导出。

设计状态稿位于 `design/`，运行时业务文本与控件均由 React 原生渲染。

## 启动

```bash
cp .env.example .env.local
pnpm install
pnpm generate:api
pnpm dev
```

默认使用符合 `docs/api/openapi.yaml` 的内置 Mock：

```text
VITE_API_MODE=mock
```

连接真实后端：

```text
VITE_API_MODE=real
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_DEV_AUTH_TOKEN=<development-token>
```

## 质量检查

```bash
pnpm typecheck
pnpm test
pnpm build
```

## 目录

```text
src/
├── api/          # 集中契约类型、Zod 边界、API Client、Mock
├── components/   # App Shell 与共享 UI
├── context/      # 项目/数据版本上下文
├── features/     # 按业务领域组织页面
├── hooks/        # Job 等可复用行为
└── lib/          # query keys 与格式化
```

页面组件不得自行声明 API 响应结构。接口和枚举变化必须先更新 OpenAPI。
