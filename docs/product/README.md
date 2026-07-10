# 产品需求文档

- `AI_Data_Analyst_Agent_产品需求规格说明书_V1.0.docx`：PRD/SRS 正式源文件。
- `rendered/`：当前正式版本的 PDF 和逐页渲染结果，仅用于版式检查。

重新生成源文档：

```bash
backend/.venv/bin/python scripts/generate_prd.py
```

生成新版本时，应替换正式源文件和 `rendered/`，不要保留
`rendered_v2`、`rendered_v3` 等历史中间目录。
