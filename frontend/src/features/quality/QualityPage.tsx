import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Filter, Play, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { QualityIssue, QualityIssueStatus, QualitySeverity } from "../../api/contracts";
import { apiClient } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { Modal } from "../../components/ui/Modal";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../components/ui/ToastProvider";
import { useAppContext } from "../../context/AppContext";
import { useJobPolling } from "../../hooks/useJobPolling";
import { queryKeys } from "../../lib/queryKeys";

const severityLabel: Record<QualitySeverity, string> = {
  low: "低", medium: "中", high: "高", critical: "严重",
};

export function QualityPage() {
  const { project, version } = useAppContext();
  const [severity, setSeverity] = useState<QualitySeverity | "all">("all");
  const [selected, setSelected] = useState<QualityIssue | null>(null);
  const [decision, setDecision] = useState<"accepted" | "ignored">("accepted");
  const [reason, setReason] = useState("");
  const [scanJobId, setScanJobId] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const navigate = useNavigate();
  const issuesQuery = useQuery({
    queryKey: queryKeys.qualityIssues(project?.project_id ?? "none", version?.version_id ?? "none"),
    queryFn: () => apiClient.listQualityIssues(project!.project_id, version!.version_id),
    enabled: Boolean(project && version),
  });
  const filtered = useMemo(
    () => issuesQuery.data?.items.filter((issue) => severity === "all" || issue.severity === severity) ?? [],
    [issuesQuery.data?.items, severity],
  );
  const scanMutation = useMutation({
    mutationFn: () => apiClient.createQualityScan(project!.project_id, version!.version_id),
    onSuccess: (job) => setScanJobId(job.job_id),
  });
  const polling = useJobPolling(scanJobId, () => {
    if (project && version) queryClient.invalidateQueries({ queryKey: queryKeys.qualityIssues(project.project_id, version.version_id) });
  });
  const decisionMutation = useMutation({
    mutationFn: () => apiClient.updateQualityIssue(project!.project_id, selected!, decision, reason.trim() || null),
    onSuccess: () => {
      setSelected(null);
      setReason("");
      pushToast(decision === "accepted" ? "问题已接受并等待进入清洗计划" : "问题已忽略");
      queryClient.invalidateQueries({ queryKey: queryKeys.qualityIssues(project!.project_id, version!.version_id) });
    },
  });

  if (!version) return <EmptyState title="暂无可扫描版本" description="请先上传数据并完成 Schema 推断。" />;

  return (
    <div className="content-page">
      <header className="page-heading">
        <div><h1>数据质量</h1><p>事实由确定性程序计算，风险解释与处置决定均保留审计记录。</p></div>
        <Button
          disabled={scanMutation.isPending || Boolean(polling.job && !polling.isTerminal)}
          icon={<Play size={16} />}
          onClick={() => scanMutation.mutate()}
          variant="primary"
        >
          {polling.job && !polling.isTerminal ? `扫描中 ${polling.job.progress}%` : "重新扫描"}
        </Button>
      </header>
      <div className="quality-toolbar">
        <span><Filter size={16} /> 严重程度</span>
        {(["all", "critical", "high", "medium", "low"] as const).map((item) => (
          <button className={severity === item ? "is-active" : ""} key={item} onClick={() => setSeverity(item)}>
            {item === "all" ? "全部" : severityLabel[item]}
          </button>
        ))}
        <Button icon={<ChevronRight size={15} />} onClick={() => navigate("/quality/cleaning")} size="sm" variant="primary">打开清洗计划</Button>
      </div>
      {issuesQuery.isLoading ? <LoadingBlock rows={7} /> : filtered.length ? (
        <div className="quality-list">
          {filtered.map((issue) => (
            <button className="quality-row" key={issue.issue_id} onClick={() => setSelected(issue)}>
              <span className={`severity-dot severity-dot--${issue.severity}`}><ShieldAlert size={18} /></span>
              <span className="quality-row__main">
                <strong>{issue.title}</strong>
                <small>{issue.explanation}</small>
              </span>
              <span className="quality-row__meta">
                <small>{issue.column ?? "全表"}</small>
                <StatusBadge status={issue.status} />
              </span>
              <ChevronRight size={17} />
            </button>
          ))}
        </div>
      ) : (
        <EmptyState title="没有匹配的问题" description="调整筛选条件，或重新运行质量扫描。" />
      )}
      <Modal
        footer={
          <>
            <Button disabled={decisionMutation.isPending} onClick={() => setSelected(null)}>取消</Button>
            <Button disabled={decision === "ignored" && !reason.trim()} onClick={() => decisionMutation.mutate()} variant="primary">
              确认处置
            </Button>
          </>
        }
        onClose={() => setSelected(null)}
        open={Boolean(selected)}
        title={selected?.title ?? "质量问题"}
      >
        {selected ? (
          <div className="issue-detail">
            <div className="issue-detail__summary"><StatusBadge status={selected.status} /><span>{severityLabel[selected.severity]}风险</span><span>{selected.column ?? "全表"}</span></div>
            <p>{selected.explanation}</p>
            <div className="metric-box"><strong>检测指标</strong><pre>{JSON.stringify(selected.metrics, null, 2)}</pre></div>
            <div className="recommendation"><strong>建议处理</strong><p>{selected.recommendation}</p></div>
            <div className="decision-options">
              <label><input checked={decision === "accepted"} name="decision" onChange={() => setDecision("accepted")} type="radio" /> 接受建议，进入清洗计划</label>
              <label><input checked={decision === "ignored"} name="decision" onChange={() => setDecision("ignored")} type="radio" /> 忽略该问题</label>
            </div>
            <label className="field"><span>决策原因 {decision === "ignored" ? "（必填）" : "（可选）"}</span><textarea onChange={(event) => setReason(event.target.value)} rows={3} value={reason} /></label>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
