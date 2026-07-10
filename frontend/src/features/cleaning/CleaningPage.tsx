import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, Eye, GripVertical, Play, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../../api/client";
import type { CleaningOperation, CleaningOperationType, CleaningPlan } from "../../api/contracts";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../components/ui/ToastProvider";
import { useAppContext } from "../../context/AppContext";
import { useJobPolling } from "../../hooks/useJobPolling";
import { queryKeys } from "../../lib/queryKeys";

const operationLabels: Record<CleaningOperationType, string> = {
  impute_missing: "缺失值填充",
  drop_duplicates: "删除重复值",
  cast_type: "类型转换",
  replace_values: "值替换",
  normalize_category: "类别标准化",
  filter_rows: "行过滤",
  add_missing_indicator: "缺失标记",
};

function newOperation(operation: CleaningOperationType): CleaningOperation {
  return {
    operation_id: `op_${crypto.randomUUID().slice(0, 7)}`,
    operation,
    column: operation === "drop_duplicates" ? "customer_id" : "income",
    parameters: operation === "impute_missing" ? { method: "median" } : {},
    reason: "由用户添加的确定性清洗操作",
    issue_ids: [],
    estimated_affected_rows: operation === "drop_duplicates" ? 12 : 481,
    risk_level: operation === "drop_duplicates" || operation === "filter_rows" ? "high" : "low",
    reversible: operation !== "drop_duplicates" && operation !== "filter_rows",
  };
}

export function CleaningPage() {
  const { project, version, setVersion } = useAppContext();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [plan, setPlan] = useState<CleaningPlan | null>(null);
  const [operations, setOperations] = useState<CleaningOperation[]>([]);
  const [reason, setReason] = useState("");
  const [riskConfirmed, setRiskConfirmed] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [compareJobId, setCompareJobId] = useState<string | null>(null);

  const plansQuery = useQuery({
    queryKey: queryKeys.cleaningPlans(project?.project_id ?? "none", version?.version_id ?? "none"),
    queryFn: () => apiClient.listCleaningPlans(project!.project_id, version!.version_id),
    enabled: Boolean(project && version),
  });
  useEffect(() => {
    const first = plansQuery.data?.items[0];
    if (first && !plan) {
      setPlan(first);
      setOperations(first.operations);
    }
  }, [plan, plansQuery.data?.items]);

  const affectedRows = useMemo(() => operations.reduce((sum, item) => sum + item.estimated_affected_rows, 0), [operations]);
  const hasHighRisk = operations.some((item) => item.risk_level === "high");
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!plan) return apiClient.createCleaningPlan(project!.project_id, version!.version_id, operations);
      return apiClient.updateCleaningPlan(project!.project_id, plan, plan.name, operations);
    },
    onSuccess: (next) => { setPlan(next); pushToast("清洗计划草稿已保存"); },
  });
  const previewMutation = useMutation({
    mutationFn: async () => {
      const current = plan ?? await apiClient.createCleaningPlan(project!.project_id, version!.version_id, operations);
      setPlan(current);
      return apiClient.previewCleaningPlan(project!.project_id, current.plan_id);
    },
    onSuccess: (job) => setJobId(job.job_id),
  });
  const previewPolling = useJobPolling(jobId, () => {
    setPlan((current) => current ? { ...current, status: "awaiting_approval", preview_artifact_id: "art_preview_cleaning" } : current);
    pushToast("清洗影响预览已生成");
  });
  const decisionMutation = useMutation({
    mutationFn: (decision: "approve" | "reject") => apiClient.decideCleaningPlan(project!.project_id, plan!.plan_id, decision, reason.trim() || null),
    onSuccess: (next) => { setPlan(next); pushToast(next.status === "approved" ? "计划已批准" : "计划已拒绝"); },
  });
  const executeMutation = useMutation({
    mutationFn: () => apiClient.executeCleaningPlan(project!.project_id, plan!.plan_id),
    onSuccess: (job) => setJobId(job.job_id),
  });
  const executionPolling = useJobPolling(plan?.status === "approved" || plan?.status === "executing" ? jobId : null, async (job) => {
    if (job.resource_id) {
      const next = await apiClient.activateDatasetVersion(project!.project_id, version!.dataset_id, job.resource_id);
      setVersion(next);
      setPlan((current) => current ? { ...current, status: "executed", result_version_id: next.version_id } : current);
      queryClient.invalidateQueries({ queryKey: queryKeys.versions(project!.project_id, next.dataset_id) });
      pushToast(`清洗完成，已激活 v${next.version_number}`);
    }
  });
  const compareMutation = useMutation({
    mutationFn: () => apiClient.compareDatasetVersions(project!.project_id, version!.dataset_id, plan!.source_version_id, plan!.result_version_id!),
    onSuccess: (job) => setCompareJobId(job.job_id),
  });
  const comparison = useJobPolling(compareJobId);

  if (!version) return <EmptyState title="暂无可清洗版本" description="请先上传数据并完成质量扫描。" />;
  if (plansQuery.isLoading) return <LoadingBlock rows={9} />;

  const previewReady = Boolean(plan?.preview_artifact_id || previewPolling.job?.status === "succeeded");
  return (
    <div className="workflow-page cleaning-page">
      <header className="workflow-heading">
        <div><h1>清洗计划</h1><p>v{version.version_number} · {version.source_file_name}</p></div>
        <div className="heading-actions">
          <Button disabled={!operations.length || saveMutation.isPending || plan?.status !== "draft"} icon={<Save size={16} />} onClick={() => saveMutation.mutate()}>保存草稿</Button>
          <Button disabled={!operations.length || previewMutation.isPending || plan?.status !== "draft"} icon={<Eye size={16} />} onClick={() => previewMutation.mutate()} variant="primary">
            {previewPolling.job && !previewPolling.isTerminal ? `生成中 ${previewPolling.job.progress}%` : "生成预览"}
          </Button>
        </div>
      </header>
      <div className="cleaning-grid">
        <aside className="operation-rail">
          <h2>操作库</h2>
          {(Object.entries(operationLabels) as [CleaningOperationType, string][]).map(([key, label]) => (
            <button key={key} onClick={() => setOperations((current) => [...current, newOperation(key)])}><Plus size={15} />{label}</button>
          ))}
        </aside>
        <section className="plan-editor">
          <header><div><h2>清洗步骤（{operations.length}）</h2><p>按顺序执行，可添加、修改或删除白名单操作。</p></div>{plan ? <StatusBadge status={plan.status} /> : null}</header>
          <div className="operation-list">
            {operations.map((operation, index) => (
              <article className="operation-row" key={operation.operation_id}>
                <GripVertical size={17} /><b>{index + 1}</b>
                <div className="operation-fields">
                  <strong>{operationLabels[operation.operation]}</strong>
                  <label>列<select value={operation.column ?? ""} onChange={(event) => setOperations((current) => current.map((item) => item.operation_id === operation.operation_id ? { ...item, column: event.target.value || null } : item))}><option>income</option><option>customer_id</option><option>plan_type</option><option>monthly_fee</option></select></label>
                </div>
                <div><small>预计影响</small><strong>{operation.estimated_affected_rows.toLocaleString()} 行</strong></div>
                <span className={`risk risk--${operation.risk_level}`}>{operation.risk_level === "high" ? "高" : operation.risk_level === "medium" ? "中" : "低"}风险</span>
                <button aria-label="删除操作" className="icon-button" onClick={() => setOperations((current) => current.filter((item) => item.operation_id !== operation.operation_id))}><Trash2 size={16} /></button>
              </article>
            ))}
          </div>
        </section>
        <aside className="approval-panel">
          <h2>预览与审批</h2>
          <div className="impact-summary"><div><span>影响</span><strong>{affectedRows.toLocaleString()} <small>行</small></strong></div><div><span>预计保留率</span><strong>99.4%</strong></div></div>
          <h3>数据对比（前 3 行）</h3>
          <div className="table-wrap"><table><thead><tr><th>客户</th><th>清洗前</th><th>清洗后</th></tr></thead><tbody><tr><td>CUST-001</td><td>income: —</td><td>income: 8,420</td></tr><tr><td>CUST-002</td><td>重复 2 条</td><td>保留最新</td></tr><tr><td>CUST-003</td><td>income: —</td><td>income: 6,980</td></tr></tbody></table></div>
          {hasHighRisk ? <div className="risk-alert"><AlertTriangle size={17} /><div><strong>包含不可逆高风险操作</strong><p>删除重复记录会永久移除 12 行数据。</p></div></div> : null}
          <label className="check-line"><input checked={riskConfirmed} onChange={(event) => setRiskConfirmed(event.target.checked)} type="checkbox" />我已理解高风险操作及回滚边界</label>
          <label className="field"><span>审批理由</span><textarea onChange={(event) => setReason(event.target.value)} rows={3} value={reason} /></label>
          <div className="approval-actions">
            <Button disabled={!previewReady || decisionMutation.isPending} onClick={() => decisionMutation.mutate("reject")}>拒绝</Button>
            {plan?.status === "approved" ? <Button disabled={executeMutation.isPending || Boolean(executionPolling.job && !executionPolling.isTerminal)} icon={<Play size={16} />} onClick={() => executeMutation.mutate()} variant="primary">执行计划</Button> :
              <Button disabled={!previewReady || (hasHighRisk && !riskConfirmed) || decisionMutation.isPending} icon={<CheckCircle2 size={16} />} onClick={() => decisionMutation.mutate("approve")} variant="primary">批准计划</Button>}
          </div>
        </aside>
      </div>
      <section className="version-result">
        <header><h2>执行与结果</h2>{executionPolling.job && !executionPolling.isTerminal ? <span>执行中 {executionPolling.job.progress}%</span> : null}</header>
        <div className="version-flow"><div><small>源数据</small><strong>v3</strong><span>82,310 行</span></div><ArrowRight /><div><small>清洗后数据</small><strong>{plan?.result_version_id ? "v4" : "等待执行"}</strong><span>{plan?.result_version_id ? "82,298 行" : "不会修改源版本"}</span></div>
          <Button disabled={!plan?.result_version_id || compareMutation.isPending} onClick={() => compareMutation.mutate()}>{comparison.job && !comparison.isTerminal ? `比较中 ${comparison.job.progress}%` : "比较版本"}</Button>
          <Button disabled={!plan?.result_version_id} icon={<RotateCcw size={15} />} onClick={async () => { const previous = await apiClient.activateDatasetVersion(project!.project_id, version.dataset_id, plan!.source_version_id); setVersion(previous); pushToast("已回滚激活版本，历史运行绑定保持不变"); }}>回滚到 v3</Button>
        </div>
      </section>
    </div>
  );
}
