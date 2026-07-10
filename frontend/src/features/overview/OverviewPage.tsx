import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ChevronRight,
  FileSpreadsheet,
  PlayCircle,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router-dom";
import { apiClient } from "../../api/client";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useAppContext } from "../../context/AppContext";
import { formatDateTime, formatNumber, shortId } from "../../lib/format";
import { queryKeys } from "../../lib/queryKeys";

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function OverviewChart({ result }: { result: unknown }) {
  const charts = asObject(result).charts;
  const chart = Array.isArray(charts) ? asObject(charts[0]) : {};
  const rows = Array.isArray(chart.data) ? chart.data.map(asObject) : [];
  const encoding = asObject(chart.encoding);
  const yKey = String(encoding.y ?? "count");
  const xKey = String(encoding.x ?? ("category" in (rows[0] ?? {}) ? "category" : "bin"));
  const maximum = Math.max(...rows.map((row) => Number(row[yKey] ?? 0)), 1);
  if (!rows.length) return <p className="panel-empty">完成一次分析运行后，这里会展示由当前数据生成的图表。</p>;
  return <div className="overview-bars" role="img" aria-label={String(chart.title ?? "最新分析图表")}>{rows.slice(0, 10).map((row, index) => { const value = Number(row[yKey] ?? 0); return <div key={`${String(row[xKey])}-${index}`}><span title={String(row[xKey] ?? index + 1)}>{String(row[xKey] ?? index + 1)}</span><i style={{ width: `${Math.max(2, value / maximum * 100)}%` }} /><b>{value.toLocaleString("zh-CN", { maximumFractionDigits: 4 })}</b></div>; })}</div>;
}

export function OverviewPage() {
  const { project, dataset, version } = useAppContext();
  const issuesQuery = useQuery({
    queryKey: queryKeys.qualityIssues(project?.project_id ?? "none", version?.version_id ?? "none"),
    queryFn: () => apiClient.listQualityIssues(project!.project_id, version!.version_id),
    enabled: Boolean(project && version),
  });
  const runsQuery = useQuery({
    queryKey: queryKeys.runs(project?.project_id ?? "none"),
    queryFn: () => apiClient.listRuns(project!.project_id),
    enabled: Boolean(project),
  });
  const latestRun = runsQuery.data?.items[0];
  const artifactsQuery = useQuery({
    queryKey: queryKeys.artifacts(project?.project_id ?? "none", latestRun?.run_id ?? "none"),
    queryFn: () => apiClient.listArtifacts(project!.project_id, latestRun!.run_id),
    enabled: Boolean(project && latestRun),
  });
  const openIssues = issuesQuery.data?.items.filter((issue) => issue.status === "open") ?? [];
  const qualityScore = Math.max(0, 100 - openIssues.reduce((total, issue) => total + ({ critical: 25, high: 15, medium: 8, low: 3 }[issue.severity] ?? 0), 0));
  const chartArtifact = artifactsQuery.data?.items.find((artifact) => artifact.type === "chart");

  return (
    <div className="overview-layout">
      <div className="overview-main">
        <header className="page-heading">
          <div>
            <h1>分析工作台</h1>
            <p>所有结论都可追溯到数据版本、代码与证据</p>
          </div>
          <Link className="text-action" to="/explore">新建分析 <ArrowRight size={16} /></Link>
        </header>

        <section aria-labelledby="dataset-summary-title" className="dataset-strip">
          <div className="dataset-strip__title">
            <span className="file-icon"><FileSpreadsheet size={23} /></span>
            <span><small id="dataset-summary-title">当前数据集</small><strong>{dataset?.name ?? "尚未上传数据"}</strong></span>
          </div>
          <dl>
            <div><dt>数据行数</dt><dd>{version ? formatNumber(version.row_count) : "—"}</dd></div>
            <div><dt>数据列数</dt><dd>{version?.column_count ?? "—"}</dd></div>
            <div><dt>当前版本</dt><dd>{version ? `v${version.version_number} · ${version.kind}` : "—"}</dd></div>
            <div><dt>更新时间</dt><dd>{formatDateTime(version?.created_at ?? null)}</dd></div>
          </dl>
        </section>

        <div className="overview-grid">
          <section className="panel quality-summary">
            <header className="panel__header">
              <h2>数据质量总览</h2>
              <Link to="/quality">查看全部问题 <ChevronRight size={15} /></Link>
            </header>
            {issuesQuery.isLoading ? <LoadingBlock rows={5} /> : (
              <div className="quality-summary__content">
                <div className="quality-score">
                  <div className="score-ring"><strong>{qualityScore}</strong><span>/100</span></div>
                  <span>质量得分</span>
                  <small>完整性、准确性、一致性、及时性</small>
                </div>
                <div className="issue-compact-list">
                  <h3>待处理问题（{openIssues.length}）</h3>
                  {openIssues.slice(0, 3).map((issue, index) => (
                    <Link className={`issue-compact ${index === 0 ? "is-selected" : ""}`} key={issue.issue_id} to="/quality">
                      <ShieldAlert aria-hidden="true" size={18} />
                      <span><strong>{issue.title}</strong><small>{issue.explanation}</small></span>
                      <ChevronRight aria-hidden="true" size={16} />
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="panel">
            <header className="panel__header">
              <h2>{chartArtifact?.name ?? "最新分析图表"}</h2>
              <Link to="/explore">查看产物 <ChevronRight size={15} /></Link>
            </header>
            <OverviewChart result={chartArtifact?.result} />
          </section>
        </div>

        <section className="panel run-panel">
          <header className="panel__header">
            <h2>最近运行</h2>
            <Link to="/explore">查看全部运行 <ChevronRight size={15} /></Link>
          </header>
          {runsQuery.isLoading ? <LoadingBlock rows={4} /> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>运行 ID</th><th>版本</th><th>状态</th><th>开始时间</th><th>结束时间</th><th>类型</th><th aria-label="查看" /></tr></thead>
                <tbody>
                  {runsQuery.data?.items.map((run) => (
                    <tr key={run.run_id}>
                      <td><strong>{shortId(run.run_id)}</strong></td>
                      <td>{run.dataset_version_id === version?.version_id ? `v${version.version_number} · ${version.kind}` : shortId(run.dataset_version_id)}</td>
                      <td><StatusBadge status={run.status} /></td>
                      <td>{formatDateTime(run.started_at)}</td>
                      <td>{formatDateTime(run.completed_at)}</td>
                      <td>{run.run_kind.toUpperCase()}</td>
                      <td><button aria-label={`查看运行 ${run.run_id}`} className="icon-button"><ChevronRight size={16} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <aside className="evidence-rail">
        <header><h2>审计与证据</h2><Sparkles aria-hidden="true" size={18} /></header>
        <div className="evidence-links">
          <Link to="/data"><FileSpreadsheet size={21} /><span><small>版本</small><strong>{version ? `v${version.version_number}` : "—"}</strong></span><ChevronRight size={16} /></Link>
          <Link to="/explore"><PlayCircle size={21} /><span><small>运行</small><strong>{latestRun ? shortId(latestRun.run_id) : "—"}</strong></span><ChevronRight size={16} /></Link>
          <Link to="/report"><ShieldAlert size={21} /><span><small>证据</small><strong>{artifactsQuery.data?.total ?? 0} 项</strong></span><ChevronRight size={16} /></Link>
        </div>
        <section className="activity-list">
          <h3>最近活动</h3>
          {version ? <article><span className="activity-icon activity-icon--blue"><FileSpreadsheet size={16} /></span><p><strong>数据版本已就绪</strong><small>{version.source_file_name} · {formatDateTime(version.created_at)}</small></p></article> : null}
          {openIssues[0] ? <article><span className="activity-icon activity-icon--amber"><ShieldAlert size={16} /></span><p><strong>发现质量问题</strong><small>{openIssues[0].title} · {formatDateTime(openIssues[0].created_at)}</small></p></article> : null}
          {latestRun ? <article><span className="activity-icon activity-icon--green"><PlayCircle size={16} /></span><p><strong>分析运行{latestRun.status === "succeeded" ? "完成" : "更新"}</strong><small>{shortId(latestRun.run_id)} · {formatDateTime(latestRun.completed_at ?? latestRun.created_at)}</small></p></article> : null}
          {!version && !latestRun ? <p className="panel-empty">上传数据后，真实处理记录会显示在这里。</p> : null}
        </section>
      </aside>
    </div>
  );
}
