# ModelScope Studio 长期运行手册

最后核对：2026-09-10

本文保留当时的 ModelScope 规则核对与环境快照，本次未重新审计该平台。
当前网站已迁至[阿里云 DataTrace](https://8.222.221.236.sslip.io/)，
上线状态以[项目状态](../development/PROJECT_STATUS.md)和[线上验收](../quality/SMALL_TRAFFIC_ACCEPTANCE.md)为准。

## 结论

DataTrace 可以在 ModelScope Docker Studio 上作为小流量公开演示或受控试点，但当前
免费资源不能提供 24×7 可用性承诺。平台对免费资源存在时长、调度和休眠限制，低访问
时可自动休眠。不应使用人工心跳规避平台休眠机制。

因此分为两个上线级别：

- **公开演示/小规模试点**：免费 CPU 资源，接受休眠和冷启动，外部化数据，使用可恢复
  部署流程。
- **24×7 正式服务**：必须使用账号可选的付费常驻资源并获得对应 SLA，或部署到
  具备 SLA、自动扩缩容和托管数据库/对象存储的生产平台。

## ModelScope 强制规则

| 领域 | 必须保证 |
| --- | --- |
| 账号 | Docker Studio 构建前完成阿里云账号绑定与实名认证 |
| 入口 | 进程监听 `0.0.0.0:7860`，不得使用平台占用的 8080 |
| HTTP Header | 应用协议不依赖 `Authorization`、`X-modelscope-*` 或 `X-studio-*` 自定义头；DataTrace 生产模式使用 HttpOnly Cookie |
| 分支 | 默认部署分支为 `master`；先 fetch/merge 后 push，禁止 force push |
| 大文件 | Git 仓库中超过 100 MB 的文件必须使用 Git LFS；运行时用户数据不得提交到仓库 |
| 密钥 | Token、口令、JWT、数据库、S3 和 LLM 凭据只通过 Studio Secrets 注入，不放入明文 Variables 或代码 |
| 可见性 | 公开 Studio 仅表示项目元数据可见；仍需验证实际 `ms.show` 应用域名对目标用户可用 |
| 资源 | 免费配额有时长和调度限制，可自动休眠；付费资源只能在当前账号的硬件 API 返回可选时使用 |
| 存储 | 普通容器层重启后不可依赖；仅 `/mnt/workspace` 是平台指定的持久化目录，但转移或重命名 Studio 仍可丢失 |
| 高可靠数据 | 用户、项目、任务元数据使用外部 PostgreSQL；上传、数据版本、Artifact 和导出使用私有 S3/OSS |

官方参考：

- <https://www.modelscope.cn/docs/studios/docker>
- <https://modelscope.cn/docs/studios/xGPU>
- <https://modelscope.cn/skills/modelscope/modelscope-studio>
- <https://modelscope.cn/.well-known/openapi.json>

## 当前 Studio 快照

2026-09-10 使用 ModelScope OpenAPI 校验：

| 项目 | 当前状态 | 判定 |
| --- | --- | --- |
| Studio | `Ascano/ai-data-analyst-agent` | 已存在 |
| SDK | `docker` | 符合项目类型 |
| 可见性 | `public` | 项目页公开 |
| 运行状态 | `Sleeping` | 当前不是常驻服务 |
| 硬件 | `platform/2v-cpu-16g-mem` | 免费、按需分配 |
| 账号可选硬件 | 仅返回上述免费 CPU | 当前无可用的付费常驻配置 |
| 远端 `master` | `5912af2fa07f82270458ed9454686f241a2ba2f1` | 落后于当前本地候选 |
| Studio Secrets | 50 个 key | 配置面已建立，但密文 value 不可反向证明有效性 |
| Studio Variables | 0 | 敏感配置未放入明文变量 |
| 历史日志 | 当前 API 返回空集 | 需下次部署后重新采集 build/run 日志 |

## 公开试点的最小长期保证

1. 使用外部 PostgreSQL，开启 TLS、自动备份/PITR，每季度完成隔离恢复。
2. 使用私有 S3/OSS，开启服务端加密、版本控制和生命周期，验证单对象恢复。
3. 每次部署使用不可变 Git SHA，通过 CI、依赖/镜像扫描、迁移和回滚门禁。
4. 部署后立即运行登录/安全头 Smoke、真实工作流和 500 请求/并发 8 小流量验收。
5. 配置外部合成监控、错误率/延迟/准备度告警和具名接收人；冷启动应与故障分开计算。
6. 禁止公开注册或仅在短窗口打开；定期轮换 JWT、管理员密码、数据库、S3 和 LLM 凭据。
7. 明确告知用户免费 Studio 可冷启动；如果业务要求持续可用，不得将免费 Studio 标注为“长期稳定”。

## 发布门禁

只有以下条件同时满足时才可以对外宣布“公开试点可用”：

- Studio 为 `Running`，build/run 日志无未接受错误；
- `ms.show` 实际应用域名可被目标用户访问；
- readiness 同时通过数据库和对象存储检查；
- 登录、上传、质量检查、分析、报告与下载闭环通过；
- 500 请求/并发 8 错误率 ≤ 1%、P95 ≤ 2 s；
- 部署 SHA、回滚 SHA、密钥轮换日期、备份/恢复证据和告警接收人已记录。

当前结论仍为 `NO-GO`：Studio 处于 `Sleeping`，远端仍是旧 SHA，账号无付费常驻硬件可选，
且目标外部 PostgreSQL/S3 与监控告警尚未在运行中实例上验证。
