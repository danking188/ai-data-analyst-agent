import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronRight,
  FileSpreadsheet,
  LockKeyhole,
  Search,
} from "lucide-react";
import { useMemo, useState } from "react";
import type { AnalysisRole, ColumnSchema, SemanticType } from "../../api/contracts";
import { apiClient } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../components/ui/ToastProvider";
import { useAppContext } from "../../context/AppContext";
import { formatDateTime, formatNumber, shortId } from "../../lib/format";
import { queryKeys } from "../../lib/queryKeys";

type DataTab = "preview" | "schema" | "diff";

const semanticOptions: SemanticType[] = [
  "numeric", "categorical", "datetime", "boolean", "identifier", "text",
  "currency", "percentage", "ordinal", "geographic_code", "unknown",
];
const roleOptions: AnalysisRole[] = [
  "feature", "target", "entity_key", "time", "identifier", "text", "excluded", "undecided",
];

function SchemaEditor({ columns, revision }: { columns: ColumnSchema[]; revision: number }) {
  const { project, version } = useAppContext();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [drafts, setDrafts] = useState<Record<string, Pick<ColumnSchema, "semantic_type" | "analysis_role">>>({});
  const mutation = useMutation({
    mutationFn: () =>
      apiClient.updateDatasetSchema(project!.project_id, version!.version_id, revision, {
        changes: Object.entries(drafts).map(([column, draft]) => ({ column, ...draft })),
        reason: "用户在字段 Schema 页面确认类型与分析角色",
      }),
    onSuccess: () => {
      setDrafts({});
      pushToast("字段定义已保存");
      queryClient.invalidateQueries({ queryKey: queryKeys.schema(project!.project_id, version!.version_id) });
    },
  });

  const updateDraft = (column: ColumnSchema, key: "semantic_type" | "analysis_role", value: string) => {
    setDrafts((current) => ({
      ...current,
      [column.name]: {
        semantic_type: current[column.name]?.semantic_type ?? column.semantic_type,
        analysis_role: current[column.name]?.analysis_role ?? column.analysis_role,
        [key]: value,
      } as Pick<ColumnSchema, "semantic_type" | "analysis_role">,
    }));
  };

  return (
    <>
      <div className="schema-toolbar">
        <p>{columns.filter((column) => !column.user_confirmed).length} 个字段需要确认</p>
        <Button disabled={!Object.keys(drafts).length || mutation.isPending} onClick={() => mutation.mutate()} variant="primary">
          {mutation.isPending ? "正在保存…" : "保存字段定义"}
        </Button>
      </div>
      <div className="table-wrap">
        <table className="schema-table">
          <thead><tr><th>字段</th><th>物理类型</th><th>语义类型</th><th>分析角色</th><th>置信度</th><th>确认状态</th></tr></thead>
          <tbody>
            {columns.map((column) => (
              <tr key={column.name}>
                <td><strong>{column.name}</strong>{column.sensitive ? <LockKeyhole aria-label="敏感字段" size={14} /> : null}</td>
                <td>{column.physical_type}</td>
                <td>
                  <select
                    aria-label={`${column.name} 语义类型`}
                    onChange={(event) => updateDraft(column, "semantic_type", event.target.value)}
                    value={drafts[column.name]?.semantic_type ?? column.semantic_type}
                  >
                    {semanticOptions.map((option) => <option key={option}>{option}</option>)}
                  </select>
                </td>
                <td>
                  <select
                    aria-label={`${column.name} 分析角色`}
                    onChange={(event) => updateDraft(column, "analysis_role", event.target.value)}
                    value={drafts[column.name]?.analysis_role ?? column.analysis_role}
                  >
                    {roleOptions.map((option) => <option key={option}>{option}</option>)}
                  </select>
                </td>
                <td><span className={column.confidence < 0.9 ? "confidence is-low" : "confidence"}>{Math.round(column.confidence * 100)}%</span></td>
                <td>{column.user_confirmed ? <span className="confirmed"><Check size={14} /> 已确认</span> : <span className="pending-confirm">待确认</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {mutation.error ? <p className="form-error">{mutation.error.message}</p> : null}
    </>
  );
}

export function DataPage() {
  const { project, dataset, version, setVersion } = useAppContext();
  const [tab, setTab] = useState<DataTab>("preview");
  const [search, setSearch] = useState("");
  const versionsQuery = useQuery({
    queryKey: queryKeys.versions(project?.project_id ?? "none", dataset?.dataset_id ?? "none"),
    queryFn: () => apiClient.listDatasetVersions(project!.project_id, dataset!.dataset_id),
    enabled: Boolean(project && dataset),
  });
  const previewQuery = useQuery({
    queryKey: queryKeys.preview(project?.project_id ?? "none", dataset?.dataset_id ?? "none", version?.version_id ?? "none"),
    queryFn: () => apiClient.previewDatasetVersion(project!.project_id, dataset!.dataset_id, version!.version_id),
    enabled: Boolean(project && dataset && version && tab === "preview"),
  });
  const schemaQuery = useQuery({
    queryKey: queryKeys.schema(project?.project_id ?? "none", version?.version_id ?? "none"),
    queryFn: () => apiClient.getDatasetSchema(project!.project_id, version!.version_id),
    enabled: Boolean(project && version && tab === "schema"),
  });
  const visibleColumns = useMemo(
    () => previewQuery.data?.columns.filter((column) => column.name.toLowerCase().includes(search.toLowerCase())) ?? [],
    [previewQuery.data?.columns, search],
  );

  if (!dataset || !version) {
    return <EmptyState title="还没有数据" description="上传 CSV、Excel 或 Parquet 后即可查看版本、字段和数据预览。" />;
  }

  return (
    <div className="data-page">
      <header className="page-heading compact">
        <div><h1>数据与版本</h1><p>原始数据只读保存，每次确认的转换都会生成新版本。</p></div>
      </header>
      <div className="data-workspace">
        <aside className="version-rail">
          <h2>版本</h2>
          {versionsQuery.isLoading ? <LoadingBlock rows={3} /> : versionsQuery.data?.items.map((item) => (
            <button
              className={`version-item ${item.version_id === version.version_id ? "is-active" : ""}`}
              key={item.version_id}
              onClick={() => setVersion(item)}
            >
              <i />
              <span><strong>v{item.version_number} · {item.kind}</strong><small>{formatDateTime(item.created_at)}</small><small>{formatNumber(item.row_count)} 行 · {item.column_count} 列</small></span>
            </button>
          ))}
        </aside>
        <section className="data-canvas">
          <header className="data-canvas__header">
            <div><FileSpreadsheet aria-hidden="true" size={23} /><span><h2>{dataset.name}</h2><p>{formatNumber(version.row_count)} 行 · {version.column_count} 列</p></span></div>
            <StatusBadge status={version.status} />
          </header>
          <div className="tabbar" role="tablist">
            <button aria-selected={tab === "preview"} className={tab === "preview" ? "is-active" : ""} onClick={() => setTab("preview")} role="tab">数据预览</button>
            <button aria-selected={tab === "schema"} className={tab === "schema" ? "is-active" : ""} onClick={() => setTab("schema")} role="tab">字段 Schema</button>
            <button aria-selected={tab === "diff"} className={tab === "diff" ? "is-active" : ""} onClick={() => setTab("diff")} role="tab">版本差异</button>
            {tab === "preview" ? (
              <label className="search-field"><Search size={16} /><input aria-label="搜索列名" onChange={(event) => setSearch(event.target.value)} placeholder="搜索列名" value={search} /></label>
            ) : null}
          </div>
          <div className="data-canvas__body">
            {tab === "preview" ? previewQuery.isLoading ? <LoadingBlock rows={8} /> : (
              <div className="table-wrap data-preview">
                <table>
                  <thead><tr><th>#</th>{visibleColumns.map((column) => <th key={column.name}>{column.name}{column.masked ? <LockKeyhole aria-label="该列已掩码" size={13} /> : null}</th>)}</tr></thead>
                  <tbody>
                    {previewQuery.data?.rows.map((row, index) => (
                      <tr key={index}><td>{index + 1}</td>{visibleColumns.map((column) => <td key={column.name}>{String(row[column.name] ?? "—")}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
                <footer className="table-footer"><span>已显示前 {previewQuery.data?.rows.length ?? 0} 行</span><Button size="sm">加载下一页 <ChevronRight size={14} /></Button></footer>
              </div>
            ) : null}
            {tab === "schema" ? schemaQuery.isLoading ? <LoadingBlock rows={8} /> : schemaQuery.data ? (
              <SchemaEditor columns={schemaQuery.data.columns} revision={schemaQuery.data.revision} />
            ) : null : null}
            {tab === "diff" ? (
              <EmptyState title="选择比较版本" description="版本差异是异步任务。选择基础版本和比较版本后，系统会生成可追溯的比较 Artifact。" />
            ) : null}
          </div>
        </section>
        <aside className="facts-rail">
          <h2>数据集信息</h2>
          <dl>
            <div><dt>文件类型</dt><dd>{dataset.source_type.toUpperCase()}</dd></div>
            <div><dt>数据规模</dt><dd>{formatNumber(version.row_count)} 行</dd></div>
            <div><dt>Hash（SHA-256）</dt><dd title={version.file_hash}>{shortId(version.file_hash)}</dd></div>
            <div><dt>创建时间</dt><dd>{formatDateTime(version.created_at)}</dd></div>
            <div><dt>父版本</dt><dd>{version.parent_version_id ? shortId(version.parent_version_id) : "原始版本"}</dd></div>
            <div><dt>状态</dt><dd><StatusBadge status={version.status} /></dd></div>
          </dl>
          {previewQuery.data?.masked_columns.length ? (
            <div className="privacy-note"><LockKeyhole size={18} /><p><strong>敏感数据已掩码</strong><span>{previewQuery.data.masked_columns.join("、")} 等字段按权限策略展示。</span></p></div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
