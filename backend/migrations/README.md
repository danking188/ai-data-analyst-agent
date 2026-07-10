# Database migrations

数据库结构只能通过 Alembic 变更，应用启动时不得调用 `metadata.create_all()`。

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic revision --autogenerate -m "describe change"
.venv/bin/alembic downgrade -1
```

生成迁移后必须：

1. 人工检查外键、唯一约束、索引和 downgrade。
2. 在空数据库执行 `upgrade head`。
3. 在已有数据库执行升级测试。
4. 执行 `alembic check`，确保模型与迁移一致。

