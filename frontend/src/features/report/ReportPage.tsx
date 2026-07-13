import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, CheckCircle2, ChevronRight, Download, FileArchive, FileCode2, FileText, Link2, Sparkles, Table2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../../api/client";
import type { Artifact, Claim, ReportExportInput } from "../../api/contracts";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../components/ui/ToastProvider";
import { useAppContext } from "../../context/AppContext";
import { useJobPolling } from "../../hooks/useJobPolling";
import { formatDateTime } from "../../lib/format";
import { queryKeys } from "../../lib/queryKeys";

const formats: Array<{ value: ReportExportInput["format"]; title: string; description: string; icon: typeof FileText }> = [
  { value: "html", title: "HTML 单页报告", description: "适合审阅与分享", icon: FileText },
  { value: "notebook", title: "Notebook", description: "包含可执行重跑入口", icon: FileCode2 },
  { value: "cleaned_data", title: "分析数据", description: "导出当前数据版本", icon: Table2 },
  { value: "manifest", title: "Manifest", description: "元数据、校验和与证据清单", icon: FileArchive },
];

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function displayValue(value: unknown) {
  if (typeof value === "number") return value.toLocaleString("zh-CN", { maximumFractionDigits: 6 });
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value ?? "-").replaceAll("_", " ");
}

export function ReportPage() {
  const { project } = useAppContext();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [selectedClaim, setSelectedClaim] = useState<Claim | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(() => window.innerWidth > 820);
  const [exportOpen, setExportOpen] = useState(false);
  const [format, setFormat] = useState<ReportExportInput["format"]>("html");
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [narrativeJobId, setNarrativeJobId] = useState<string | null>(null);
  const capabilitiesQuery = useQuery({ queryKey: ["system", "capabilities"], queryFn: () => apiClient.getCapabilities() });
  const runsQuery = useQuery({ queryKey: queryKeys.runs(project?.project_id ?? "none"), queryFn: () => apiClient.listRuns(project!.project_id), enabled: Boolean(project) });
  const run = runsQuery.data?.items.find((item) => item.status === "succeeded");
  const claimsQuery = useQuery({ queryKey: queryKeys.claims(project?.project_id ?? "none", run?.run_id ?? "none"), queryFn: () => apiClient.listClaims(project!.project_id, run!.run_id), enabled: Boolean(project && run) });
  const artifactsQuery = useQuery({ queryKey: queryKeys.artifacts(project?.project_id ?? "none", run?.run_id ?? "none"), queryFn: () => apiClient.listArtifacts(project!.project_id, run!.run_id), enabled: Boolean(project && run) });
  const publishableClaims = useMemo(() => claimsQuery.data?.items.filter((item) => item.validation_status === "passed") ?? [], [claimsQuery.data?.items]);
  useEffect(() => { if (!selectedClaim && publishableClaims[0]) setSelectedClaim(publishableClaims[0]); }, [publishableClaims, selectedClaim]);
  const exportMutation = useMutation({
    mutationFn: () => apiClient.createReportExport(project!.project_id, {
      run_id: run!.run_id,
      format,
      claim_ids: publishableClaims.map((item) => item.claim_id),
      include_code: true,
      include_evidence: true,
      data_format: format === "cleaned_data" ? "csv" : null,
    }),
    onSuccess: (job) => setExportJobId(job.job_id),
    onError: (error) => pushToast(error instanceof Error ? error.message : "导出任务创建失败"),
  });
  const exportPolling = useJobPolling(exportJobId, async (job) => {
    if (!job.resource_id) return;
    const download = await apiClient.downloadArtifact(project!.project_id, job.resource_id);
    pushToast(`已生成并下载 ${download.file_name}`);
    queryClient.invalidateQueries({ queryKey: queryKeys.artifacts(project!.project_id, run!.run_id) });
  });
  const narrativeMutation = useMutation({
    mutationFn: () => apiClient.createReportExport(project!.project_id, {
      run_id: run!.run_id,
      format: "ai_narrative",
      claim_ids: publishableClaims.map((item) => item.claim_id),
      include_code: false,
      include_evidence: true,
      data_format: null,
    }),
    onSuccess: (job) => setNarrativeJobId(job.job_id),
    onError: (error) => pushToast(error instanceof Error ? error.message : "AI 解读任务创建失败"),
  });
  const narrativePolling = useJobPolling(narrativeJobId, async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.artifacts(project!.project_id, run!.run_id) });
    pushToast("AI 证据解读已生成");
  });
  const artifacts = artifactsQuery.data?.items ?? [];
  const evidenceArtifacts = artifacts.filter((item) => selectedClaim?.evidence_ids.includes(item.artifact_id));
  if (runsQuery.isLoading || claimsQuery.isLoading || artifactsQuery.isLoading) return <LoadingBlock rows={10} />;
  if (!run) return <EmptyState title="暂无可发布报告" description="只有基于真实数据且验证完成的分析运行才能生成正式报告。" />;
  const datasetOverview = asObject(artifacts.find((item) => item.type === "metric" && "row_count" in asObject(item.result))?.result);
  const modelResult = asObject(artifacts.find((item) => item.type === "model")?.result);
  const modelMetrics = asObject(asObject(artifacts.find((item) => item.type === "metric" && "metrics" in asObject(item.result))?.result).metrics);
  const limitations = [...new Set(publishableClaims.flatMap((claim) => claim.limitations))];
  const narrativeArtifact = artifacts.filter((item) => item.producer === "llm_report_narrative").at(-1);
  const narrative = asObject(narrativeArtifact?.result);
  const narrativeFindings = Array.isArray(narrative.findings)
    ? narrative.findings.map(asObject).filter((item) => typeof item.text === "string")
    : [];
  const llmEnabled = capabilitiesQuery.data?.llm.evidence_narrative === true;
  const openCitation = (citationId: string) => {
    const claim = publishableClaims.find((item) => item.claim_id === citationId || item.evidence_ids.includes(citationId));
    if (claim) {
      setSelectedClaim(claim);
      setEvidenceOpen(true);
    }
  };
  return (
    <div className={`report-workspace ${evidenceOpen ? "has-evidence" : ""} ${exportOpen ? "has-export" : ""}`}>
      <article className="report-document">
        <header className="report-header"><div><h1>分析报告</h1><p>{project?.name ?? "数据分析项目"} · 运行 {run.run_id}</p><small>完成时间：{run.completed_at ? formatDateTime(run.completed_at) : "-"} · 数据版本：{run.dataset_version_id}</small></div><div>{llmEnabled ? <Button disabled={narrativeMutation.isPending || Boolean(narrativePolling.job && !narrativePolling.isTerminal)} icon={<Sparkles size={16} />} onClick={() => narrativeMutation.mutate()}>{narrativePolling.job && !narrativePolling.isTerminal ? `解读中 ${narrativePolling.job.progress}%` : narrativeArtifact ? "重新解读" : "AI 解读"}</Button> : null}<Button icon={<FileText size={16} />} onClick={() => { setFormat("html"); setExportOpen(true); }}>导出报告</Button><Button icon={<Download size={16} />} onClick={() => { setFormat("manifest"); setExportOpen(true); }} variant="primary">下载证据包</Button></div></header>
        {narrativeArtifact ? <section className="report-section ai-narrative"><header><div><Sparkles size={17} /><h2>AI 证据解读</h2></div><small>{String(asObject(narrativeArtifact.parameters).model ?? "-")} · {String(asObject(narrativeArtifact.parameters).prompt_version ?? narrativeArtifact.producer_version)}</small></header><p>{String(narrative.summary ?? "")}</p>{narrativeFindings.length ? <ol>{narrativeFindings.map((finding, index) => <li key={`${index}-${String(finding.text)}`}><p>{String(finding.text)}</p><div>{Array.isArray(finding.citation_ids) ? finding.citation_ids.map((citation) => <button key={String(citation)} onClick={() => openCitation(String(citation))}><Link2 size={12} />{String(citation)}</button>) : null}</div></li>)}</ol> : null}</section> : null}
        <section className="report-section"><h2>1. 经验证结论</h2>{publishableClaims.length ? <div className="claim-list">{publishableClaims.map((claim, index) => <button className={selectedClaim?.claim_id === claim.claim_id ? "is-selected" : ""} key={claim.claim_id} onClick={() => { setSelectedClaim(claim); setEvidenceOpen(true); }}><b>{index + 1}</b><StatusBadge status={claim.validation_status} /><span>{claim.text}<small>局限：{claim.limitations[0] ?? "无补充限制"}</small></span><em>证据 {claim.evidence_ids.length}</em><ChevronRight size={16} /></button>)}</div> : <EmptyState title="暂无通过验证的结论" description="验证失败或缺少证据的结论不会进入正式报告。" />}</section>
        <section className="report-section prose">
          <h2>2. 数据概况</h2><table><tbody>{Object.entries(datasetOverview).map(([key, value]) => <tr key={key}><th>{key.replaceAll("_", " ")}</th><td>{displayValue(value)}</td></tr>)}</tbody></table>
          <h2>3. 分析方法</h2><p>本次运行使用 {displayValue(modelResult.model_family)}，策略为 {displayValue(modelResult.strategy)}，目标字段为 {displayValue(modelResult.target)}。结果绑定运行、数据版本、随机种子及工具版本，可通过 Manifest 复核。</p>
          <h2>4. 模型指标</h2>{Object.keys(modelMetrics).length ? <table><thead><tr><th>指标</th><th>值</th></tr></thead><tbody>{Object.entries(modelMetrics).map(([key, value]) => <tr key={key}><td>{key.toUpperCase().replaceAll("_", "-")}</td><td>{displayValue(value)}</td></tr>)}</tbody></table> : <p>当前运行没有模型指标 Artifact。</p>}
          <h2>5. 分析产物</h2><ul>{artifacts.filter((artifact) => artifact.status === "ready").map((artifact) => <li key={artifact.artifact_id}>{artifact.name}（{artifact.type}，校验和 {artifact.checksum.slice(0, 20)}…）</li>)}</ul>
          <h2>6. 局限</h2>{limitations.length ? <ul>{limitations.map((item) => <li key={item}>{item}</li>)}</ul> : <p>当前通过验证的结论没有额外局限说明。</p>}
        </section>
      </article>
      {evidenceOpen ? <EvidenceDrawer claim={selectedClaim} artifacts={evidenceArtifacts} onClose={() => setEvidenceOpen(false)} /> : null}
      {exportOpen ? <aside className="export-drawer"><header><h2>导出报告</h2><button aria-label="关闭导出" className="icon-button" onClick={() => setExportOpen(false)}><X size={18} /></button></header><h3>导出格式</h3><div className="format-list">{formats.map(({ value, title, description, icon: Icon }) => <label className={format === value ? "is-selected" : ""} key={value}><Icon size={18} /><span><strong>{title}</strong><small>{description}</small></span><input checked={format === value} name="format" onChange={() => setFormat(value)} type="radio" /></label>)}</div><div className="export-status"><h3>导出作业</h3>{exportPolling.job ? <><div><span>{exportPolling.job.current_step ?? (exportPolling.job.status === "succeeded" ? "文件已生成" : "等待处理")}</span><strong>{exportPolling.job.progress}%</strong></div><progress max="100" value={exportPolling.job.progress} />{exportPolling.job.status === "succeeded" ? <p><CheckCircle2 size={15} /> 文件已经开始下载。</p> : exportPolling.job.error ? <p>{exportPolling.job.error.message}</p> : null}</> : <p>仅导出验证通过的结论，并附带真实 Artifact 校验信息。</p>}</div><Button disabled={exportMutation.isPending || Boolean(exportPolling.job && !exportPolling.isTerminal)} onClick={() => exportMutation.mutate()} variant="primary">{exportPolling.job?.status === "failed" ? "重试导出" : "生成并下载"}</Button></aside> : null}
    </div>
  );
}

function EvidenceDrawer({ claim, artifacts, onClose }: { claim: Claim | null; artifacts: Artifact[]; onClose: () => void }) {
  const { project } = useAppContext();
  const { pushToast } = useToast();
  return <aside className="evidence-drawer"><header><h2>证据链</h2><button aria-label="关闭证据" className="icon-button" onClick={onClose}><X size={18} /></button></header>{claim ? <><h3>当前选中结论</h3><div className="selected-claim"><b>{claim.level}</b><p>{claim.text}</p></div><h3>证据路径</h3><div className="evidence-path"><span>Claim</span><ChevronRight/><span>Artifact</span><ChevronRight/><span>Run</span><ChevronRight/><span>{claim.dataset_version_id}</span></div><h3>来源 Artifact（{artifacts.length}）</h3><div className="source-list">{artifacts.map((artifact) => <button key={artifact.artifact_id} onClick={async () => { if (artifact.downloadable) { const download = await apiClient.downloadArtifact(project!.project_id, artifact.artifact_id); pushToast(`正在下载 ${download.file_name}`); } else { pushToast(`${artifact.name} 已绑定到当前结论`); } }}><span>{artifact.type === "chart" ? <BarChart3 size={16}/> : artifact.type === "table" ? <Table2 size={16}/> : <Link2 size={16}/>}</span><p><strong>{artifact.name}</strong><small>{artifact.artifact_id}</small></p><ChevronRight size={15}/></button>)}</div><h3>验证详情</h3><dl className="evidence-detail"><div><dt>验证状态</dt><dd><StatusBadge status={claim.validation_status}/></dd></div><div><dt>结论等级</dt><dd>L{claim.level}</dd></div><div><dt>数据版本</dt><dd>{claim.dataset_version_id}</dd></div></dl><h3>局限（来自结论）</h3><ul className="limitation-list">{claim.limitations.map((item) => <li key={item}>{item}</li>)}</ul></> : null}</aside>;
}
