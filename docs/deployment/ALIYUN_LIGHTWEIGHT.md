# 阿里云轻量应用服务器部署

当前网站：[DataTrace](https://8.222.221.236.sslip.io/)。实际实例位于新加坡，已于
2026-09-11 完成整机重启恢复；2026-09-15 重新完成注册、上传到报告、真实 Agent、浏览器和
500 请求小流量验收。
验收记录见[小流量验收](../quality/SMALL_TRAFFIC_ACCEPTANCE.md)。

以下命令对应仓库内的阿里云轻量运维实现。部署配置、巡检、备份和端到端验收脚本必须与
应用代码使用同一个 Git 版本，避免线上状态与仓库文档分离。

该配置面向单个 DataTrace 项目和小规模访问，目标规格为 **2 核 2GB、Ubuntu 24.04、
至少 40GB ESSD**。它使用单应用容器、宿主机持久化目录和 Caddy 自动 HTTPS，内存上限
为 1400MB，并由宿主机提供 2GB Swap。不要在此档位同时运行第二个数据分析项目。

这是一套“最低可运行”而不是“完整高可用”拓扑：单机故障仍会造成中断；SQLite 与上传
文件必须额外备份到 OSS 或另一台机器。部署脚本会限制容器日志体积，每天生成一份
本机数据快照并保留 14 天，健康检查连续失败 3 次时自动重启应用。需要更高可靠性时，迁移到根目录生产 Compose、
外部 PostgreSQL 和私有 OSS。

## 1. 购买前选择

- 产品：轻量应用服务器。
- 地域：选择主要用户最近、且活动价最低的中国内地地域。
- 镜像：Ubuntu 24.04 纯净系统镜像。
- 套餐：2 vCPU / 2GB 为最低建议值；不要选择 0.5GB 或 1GB。
- 公网：至少 3Mbps；磁盘至少 40GB。
- 时长：首次部署选最短可购周期，验证稳定后再续费或转年付。

中国内地公网域名正式对外服务前需要完成 ICP 备案。DNS 的 A 记录应指向服务器公网
IPv4；80/443 端口开放后，Caddy 会自动申请和续期 HTTPS 证书。

## 2. 初始化服务器

将仓库放到服务器（建议 `/opt/datatrace/app`），然后执行：

```bash
cd /opt/datatrace/app
chmod +x scripts/bootstrap_aliyun_lite.sh scripts/deploy_aliyun_lite.sh
sudo ./scripts/bootstrap_aliyun_lite.sh
```

脚本仅支持 Ubuntu，会安装 Docker Compose、UFW 和 fail2ban，保留 SSH，并开放
80/443 TCP 与 443 UDP。它只会在主机没有 Swap 时创建 `/swapfile`。

## 3. 配置并上线

```bash
cd /opt/datatrace/app/deploy/aliyun-lite
cp env.example .env
chmod 600 .env
```

将 `DOMAIN`、`CORS_ORIGINS` 和 `TRUSTED_HOSTS` 改成真实域名；用密码
生成器生成 `JWT_SECRET` 和 `LOGIN_PASSWORD`。不要把 `.env` 提交到 Git。

需要开放自助注册时，将 `REGISTRATION_ENABLED=true`。首次部署、尚无 `.env` 时，也可以生成配置：

```bash
cd /opt/datatrace/app
python3 scripts/configure_aliyun_lite_env.py --enable-registration 你的域名
```

已有部署不要重复运行配置生成器：它会覆盖 `.env` 并重新生成 JWT 密钥与初始密码。
已有用户的数据库密码不会随之更新；调整注册开关时只修改现有配置中的对应变量并重新部署。

### 启用真实 Agent（DeepSeek）

建议使用项目专用 Key，并将以下配置写入仅 root 可读的 `.env`：

```dotenv
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=你的项目专用密钥
LLM_MODEL=deepseek-flash
LLM_REPLAY_ALLOWED_MODELS=deepseek-flash
LLM_STRUCTURED_OUTPUT_MODE=prompt
LLM_ENABLE_THINKING=
LLM_THINKING_MODE=disabled
LLM_MAX_OUTPUT_TOKENS=2048
LLM_MAX_INPUT_TOKENS=12000
LLM_DAILY_TOKEN_BUDGET_PER_USER=50000
LLM_MAX_CONCURRENT_TURNS_PER_PROJECT=1
```

`deepseek-flash` 用于当前小规模试点，以较低成本完成结构化意图识别、计划与证据叙述；
`LLM_THINKING_MODE=disabled` 用于确保复杂任务的 Token 预算留给最终 JSON 输出。模型
训练仍由 sklearn 确定性 Worker 执行。公开注册时必须保留单用户 Token 预算、单项目并发限制、
熔断和审计；需要灰度时设置 `LLM_CANARY_SUBJECTS`。

注册用户名为 3-32 位字母、数字、点、下划线或连字符；密码为 12-128 个字符且不能包含
用户名。注册成功后会直接建立登录会话。项目、上传文件、分析结果和报告均按账号隔离，
但该模式仍是公开注册：正式开放前应结合站点用途决定是否增加邮箱验证、邀请码或人工审核。

确认域名 A 记录已经生效后：

```bash
cd /opt/datatrace/app
sudo ./scripts/deploy_aliyun_lite.sh
```

上线后运行：

```bash
FRONTEND_URL="https://你的域名" \
BACKEND_URL="https://你的域名/api/v1" \
LOGIN_USERNAME=analyst \
LOGIN_PASSWORD='从服务器密钥文件读取' \
./scripts/deploy_smoke.sh
```

再按 `SMALL_TRAFFIC_ACCEPTANCE.md` 运行 500 请求、并发 8 的验收。开放给用户前，至少
配置阿里云监控告警、到期自动续费或到期提醒、每日异机备份和季度恢复演练。脚本自动建立的
本机备份只能处理应用误操作，不能代替 OSS 或另一台主机上的异机备份。

启用 LLM 后还必须执行包含真实模型调用的完整验收：

```bash
LOGIN_USERNAME=analyst \
LOGIN_PASSWORD='从服务器密钥文件读取' \
python3 scripts/production_workflow_smoke.py \
  --base-url "https://你的域名" \
  --exercise-llm
```

该命令使用一次性项目覆盖上传、质量扫描、模型训练、证据与报告导出，并额外验证 AI 证据
解读、Assistant 只读工具、分析计划、人工确认和确认后的受控执行。成功后默认归档测试项目。
