import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { apiClient } from "../../api/client";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useAppContext } from "../../context/AppContext";
import { queryKeys } from "../../lib/queryKeys";
import { ArtifactViewer } from "../explore/ExplorePage";

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function label(value: unknown) {
  return String(value ?? "-").replaceAll("_", " ");
}

export function ModelPage() {
  const { project } = useAppContext();
  const runsQuery = useQuery({ queryKey: queryKeys.runs(project?.project_id ?? "none"), queryFn: () => apiClient.listRuns(project!.project_id), enabled: Boolean(project) });
  const run = runsQuery.data?.items.find((item) => ["model", "full"].includes(item.run_kind) && item.status === "succeeded")
    ?? runsQuery.data?.items.find((item) => ["model", "full"].includes(item.run_kind));
  const artifactsQuery = useQuery({ queryKey: queryKeys.artifacts(project?.project_id ?? "none", run?.run_id ?? "none"), queryFn: () => apiClient.listArtifacts(project!.project_id, run!.run_id), enabled: Boolean(project && run) });
  if (runsQuery.isLoading || artifactsQuery.isLoading) return <LoadingBlock rows={8} />;
  if (!run) return <EmptyState title="暂无模型运行" description="先在探索页面选择真实字段、确认 AnalysisSpec 并启动运行。" />;
  const artifacts = artifactsQuery.data?.items ?? [];
  const model = artifacts.find((item) => item.type === "model");
  const metric = artifacts.find((item) => item.type === "metric" && Object.keys(asObject(asObject(item.result).metrics)).length > 0);
  const modelResult = asObject(model?.result);
  const metricResult = asObject(asObject(metric?.result).metrics);
  const firstMetric = Object.entries(metricResult)[0];
  const split = asObject(modelResult.split);
  const leakage = asObject(modelResult.leakage_controls);
  return <div className="workflow-page"><header className="workflow-heading"><div><h1>基线模型</h1><p>结果来自运行 {run.run_id}，并绑定真实输入版本与可复现参数。</p></div><StatusBadge status={run.status} /></header><section className="model-summary"><div><span>模型族</span><strong>{label(modelResult.model_family)}</strong><small>{label(modelResult.strategy)}</small></div><div><span>{firstMetric?.[0]?.toUpperCase().replaceAll("_", "-") ?? "评估指标"}</span><strong>{typeof firstMetric?.[1] === "number" ? firstMetric[1].toLocaleString("zh-CN", { maximumFractionDigits: 4 }) : "-"}</strong><small>测试集 {Number(split.test_rows ?? 0).toLocaleString("zh-CN")} 行</small></div><div><span>泄露控制</span><strong><CheckCircle2 size={19} /> {leakage.split_before_fit ? "已通过" : "待确认"}</strong><small>{label(leakage.fit_scope)}</small></div><div><span>数据版本</span><strong>{run.dataset_version_id}</strong><small>训练集 {Number(split.train_rows ?? 0).toLocaleString("zh-CN")} 行</small></div></section><ArtifactViewer artifacts={artifacts} /></div>;
}
