import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Circle, Download, Play, Save, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../../api/client";
import type { AnalysisSpec, AnalysisSpecInput, AnalysisRun, Artifact, ColumnSchema, DatasetSchema } from "../../api/contracts";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../components/ui/ToastProvider";
import { useAppContext } from "../../context/AppContext";
import { useJobPolling } from "../../hooks/useJobPolling";
import { queryKeys } from "../../lib/queryKeys";

const metricCatalog: Record<AnalysisSpecInput["task"], Array<{ value: string; label: string }>> = {
  binary_classification: [
    { value: "accuracy", label: "Accuracy" }, { value: "roc_auc", label: "ROC-AUC" },
    { value: "f1", label: "F1" }, { value: "precision", label: "Precision" },
    { value: "recall", label: "Recall" }, { value: "log_loss", label: "Log Loss" },
  ],
  multiclass_classification: [
    { value: "accuracy", label: "Accuracy" }, { value: "f1", label: "F1" },
    { value: "precision", label: "Precision" }, { value: "recall", label: "Recall" },
    { value: "log_loss", label: "Log Loss" },
  ],
  regression: [
    { value: "mae", label: "MAE" }, { value: "rmse", label: "RMSE" },
    { value: "r2", label: "R²" }, { value: "mape", label: "MAPE" },
  ],
  descriptive: [],
  comparison: [],
  statistical_test: [],
};

const taskLabels: Record<AnalysisSpecInput["task"], string> = {
  binary_classification: "二分类预测",
  multiclass_classification: "多分类预测",
  regression: "回归预测",
  descriptive: "描述性分析",
  comparison: "分组比较",
  statistical_test: "统计检验",
};

function inferTask(target: ColumnSchema | undefined): AnalysisSpecInput["task"] {
  return target?.semantic_type === "numeric" || ["integer", "float"].includes(target?.physical_type ?? "")
    ? "regression"
    : "binary_classification";
}

function defaultForm(versionId: string, schema: DatasetSchema): AnalysisSpecInput {
  const eligible = schema.columns.filter((column) => !column.sensitive && column.analysis_role !== "excluded");
  const target = eligible.find((column) => column.analysis_role === "target")
    ?? [...eligible].reverse().find((column) => !["identifier", "entity_key", "time"].includes(column.analysis_role));
  const task = inferTask(target);
  const entity = eligible.find((column) => ["entity_key", "identifier"].includes(column.analysis_role));
  const time = eligible.find((column) => column.analysis_role === "time" || column.semantic_type === "datetime");
  const includedColumns = eligible
    .filter((column) => column.name !== target?.name && !["entity_key", "identifier", "time"].includes(column.analysis_role))
    .map((column) => column.name);
  return {
    name: `${taskLabels[task]} · ${target?.name ?? "全量字段"}`,
    dataset_version_id: versionId,
    task,
    target: target?.name ?? null,
    entity_key: entity?.name ?? null,
    time_column: time?.name ?? null,
    prediction_time_description: "仅使用结果发生前可获得的字段进行评估。",
    split_strategy: task === "regression" ? "random" : "stratified",
    group_column: null,
    metrics: metricCatalog[task].slice(0, 4).map((item) => item.value),
    included_columns: includedColumns,
    excluded_columns: schema.columns.filter((column) => column.sensitive || column.analysis_role === "excluded").map((column) => column.name),
    random_seed: 42,
    causal_interpretation_allowed: false,
  };
}

export function ExplorePage() {
  const { project, version } = useAppContext();
  const { pushToast } = useToast();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [spec, setSpec] = useState<AnalysisSpec | null>(null);
  const [form, setForm] = useState<AnalysisSpecInput | null>(null);
  const [runJobId, setRunJobId] = useState<string | null>(null);
  const schemaQuery = useQuery({
    queryKey: queryKeys.schema(project?.project_id ?? "none", version?.version_id ?? "none"),
    queryFn: () => apiClient.getDatasetSchema(project!.project_id, version!.version_id),
    enabled: Boolean(project && version),
  });
  const specsQuery = useQuery({
    queryKey: queryKeys.analysisSpecs(project?.project_id ?? "none", version?.version_id ?? "none"),
    queryFn: () => apiClient.listAnalysisSpecs(project!.project_id, version!.version_id),
    enabled: Boolean(project && version),
  });
  const runsQuery = useQuery({
    queryKey: queryKeys.runs(project?.project_id ?? "none"), queryFn: () => apiClient.listRuns(project!.project_id), enabled: Boolean(project),
  });
  const activeRun = runsQuery.data?.items[0] ?? null;
  const artifactsQuery = useQuery({
    queryKey: queryKeys.artifacts(project?.project_id ?? "none", activeRun?.run_id ?? "none"),
    queryFn: () => apiClient.listArtifacts(project!.project_id, activeRun!.run_id), enabled: Boolean(project && activeRun),
  });
  useEffect(() => {
    if (!form && version && schemaQuery.data) {
      const first = specsQuery.data?.items[0];
      setSpec(first ?? null);
      setForm(first ? { ...first } : defaultForm(version.version_id, schemaQuery.data));
    }
  }, [form, schemaQuery.data, specsQuery.data?.items, version]);
  const saveMutation = useMutation({
    mutationFn: () => spec ? apiClient.updateAnalysisSpec(project!.project_id, spec, form!) : apiClient.createAnalysisSpec(project!.project_id, form!),
    onSuccess: (next) => { setSpec(next); pushToast("AnalysisSpec 草稿已保存"); },
  });
  const runMutation = useMutation({
    mutationFn: async () => {
      let current = spec ?? await apiClient.createAnalysisSpec(project!.project_id, form!);
      if (current.status !== "confirmed") current = await apiClient.confirmAnalysisSpec(project!.project_id, current.spec_id);
      setSpec(current);
      return apiClient.createRun(project!.project_id, current.spec_id, current.dataset_version_id);
    },
    onSuccess: (job) => setRunJobId(job.job_id),
  });
  useJobPolling(runJobId, () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.runs(project!.project_id) });
    pushToast("分析运行已完成");
  });
  const cancelMutation = useMutation({
    mutationFn: () => apiClient.cancelRun(project!.project_id, activeRun!.run_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.runs(project!.project_id) }),
  });
  const availableMetrics = useMemo(() => form ? metricCatalog[form.task] : [], [form]);
  const updateTask = (task: AnalysisSpecInput["task"]) => {
    if (!form) return;
    setForm({
      ...form,
      task,
      metrics: metricCatalog[task].slice(0, 4).map((item) => item.value),
      split_strategy: task === "regression" ? "random" : "stratified",
    });
  };
  if (!version) return <EmptyState title="暂无分析数据" description="请先上传并确认一个数据版本。" />;
  if (!form || specsQuery.isLoading || schemaQuery.isLoading) return <LoadingBlock rows={8} />;
  const columns = schemaQuery.data?.columns ?? [];
  return (
    <div className="workflow-page explore-page">
      <header className="workflow-heading"><div><h1>分析设计</h1><p>{version.source_file_name} · v{version.version_number} · {columns.length} 个字段</p></div><Button disabled={saveMutation.isPending || spec?.status === "confirmed"} icon={<Save size={16} />} onClick={() => saveMutation.mutate()}>保存草稿</Button></header>
      <div className="wizard-layout">
        <section className="wizard-main">
          <nav className="wizard-steps" aria-label="分析设置步骤">{["分析目标", "字段角色", "拆分策略", "确认运行"].map((label, index) => <button className={step === index + 1 ? "is-active" : step > index + 1 ? "is-done" : ""} key={label} onClick={() => setStep(index + 1)}><span>{step > index + 1 ? <Check size={15} /> : index + 1}</span>{label}</button>)}</nav>
          <div className="analysis-form">
            <section>
              <h2>任务与目标</h2>
              <label className="field"><span>任务类型</span><select value={form.task} onChange={(event) => updateTask(event.target.value as AnalysisSpecInput["task"])}><option value="binary_classification">二分类预测</option><option value="multiclass_classification">多分类预测</option><option value="regression">回归预测</option></select></label>
              <label className="field"><span>目标字段</span><select value={form.target ?? ""} onChange={(event) => setForm({ ...form, target: event.target.value || null, included_columns: form.included_columns.filter((item) => item !== event.target.value) })}><option value="">请选择</option>{columns.filter((column) => !column.sensitive).map((column) => <option key={column.name} value={column.name}>{column.name} · {column.semantic_type}</option>)}</select></label>
              <label className="field"><span>实体键（可选）</span><select value={form.entity_key ?? ""} onChange={(event) => setForm({ ...form, entity_key: event.target.value || null })}><option value="">不设置</option>{columns.map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}</select></label>
              <label className="field"><span>时间列（可选）</span><select value={form.time_column ?? ""} onChange={(event) => setForm({ ...form, time_column: event.target.value || null })}><option value="">不设置</option>{columns.filter((column) => column.semantic_type === "datetime" || column.physical_type === "datetime").map((column) => <option key={column.name} value={column.name}>{column.name}</option>)}</select></label>
            </section>
            <section>
              <h2>字段与拆分</h2>
              <label className="field"><span>预测时点说明</span><textarea rows={3} value={form.prediction_time_description ?? ""} onChange={(event) => setForm({ ...form, prediction_time_description: event.target.value })} /></label>
              <label className="field"><span>拆分策略</span><select value={form.split_strategy} onChange={(event) => setForm({ ...form, split_strategy: event.target.value as AnalysisSpecInput["split_strategy"] })}><option value="random">随机拆分</option><option value="stratified">分层随机拆分</option><option value="temporal">时间拆分</option><option value="group">分组拆分</option></select></label>
              <label className="field"><span>随机种子</span><input min="0" type="number" value={form.random_seed} onChange={(event) => setForm({ ...form, random_seed: Number(event.target.value) })} /></label>
              <div className="metric-options"><span>评估指标</span>{availableMetrics.map((metric) => <label key={metric.value}><input checked={form.metrics.includes(metric.value)} type="checkbox" onChange={(event) => setForm({ ...form, metrics: event.target.checked ? [...form.metrics, metric.value] : form.metrics.filter((item) => item !== metric.value) })} />{metric.label}</label>)}</div>
              <div className="metric-options feature-options"><span>参与建模字段</span>{columns.filter((column) => !column.sensitive && column.name !== form.target).map((column) => <label key={column.name}><input checked={form.included_columns.includes(column.name)} type="checkbox" onChange={(event) => setForm({ ...form, included_columns: event.target.checked ? [...form.included_columns, column.name] : form.included_columns.filter((item) => item !== column.name), excluded_columns: event.target.checked ? form.excluded_columns.filter((item) => item !== column.name) : [...new Set([...form.excluded_columns, column.name])] })} />{column.name}</label>)}</div>
            </section>
          </div>
        </section>
        <aside className="run-confirm">
          <h2>运行确认</h2><h3>真实数据约束</h3><ul><li>输入绑定数据版本 {version.version_id}。</li><li>敏感字段不会进入自动分析图表。</li><li>模型先拆分数据，再仅使用训练集拟合 Baseline。</li></ul>
          <dl><div><dt>任务类型</dt><dd>{taskLabels[form.task]}</dd></div><div><dt>目标字段</dt><dd>{form.target ?? "未选择"}</dd></div><div><dt>参与字段</dt><dd>{form.included_columns.length} 个</dd></div><div><dt>拆分策略</dt><dd>{form.split_strategy}</dd></div><div><dt>评估指标</dt><dd>{form.metrics.map((value) => availableMetrics.find((item) => item.value === value)?.label ?? value).join(", ")}</dd></div></dl>
          <Button disabled={runMutation.isPending || !form.target || !form.metrics.length || !form.included_columns.length} icon={<Play size={16} />} onClick={() => runMutation.mutate()} variant="primary">确认并运行</Button>
        </aside>
      </div>
      <RunProgress run={activeRun} onCancel={() => cancelMutation.mutate()} />
      <ArtifactViewer artifacts={artifactsQuery.data?.items ?? []} />
    </div>
  );
}

function RunProgress({ run, onCancel }: { run: AnalysisRun | null; onCancel: () => void }) {
  if (!run) return null;
  return <section className="run-progress"><header><div><h2>运行进度</h2><StatusBadge status={run.status} /><span>{run.progress}%</span></div>{run.status === "running" ? <Button icon={<Square size={13} />} onClick={onCancel}>取消运行</Button> : null}</header><div className="step-track">{run.steps.map((item) => <div className={`run-step run-step--${item.status}`} key={item.step_id}>{item.status === "succeeded" ? <Check size={15} /> : <Circle size={14} />}<span><strong>{item.order}. {item.name}</strong><small>{item.status}</small></span></div>)}</div></section>;
}

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function formatValue(value: unknown) {
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString("zh-CN") : value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  return String(value ?? "-");
}

function MetricArtifact({ artifact }: { artifact: Artifact }) {
  const result = asObject(artifact.result) ?? {};
  const metrics = asObject(result.metrics) ?? result;
  return <div className="artifact-metrics">{Object.entries(metrics).filter(([, value]) => typeof value !== "object").map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{formatValue(value)}</strong></div>)}</div>;
}

function ChartArtifact({ artifact }: { artifact: Artifact }) {
  const charts = asObject(artifact.result)?.charts;
  if (!Array.isArray(charts) || !charts.length) return <pre>{JSON.stringify(artifact.result, null, 2)}</pre>;
  return <div className="chart-stack">{charts.map((rawChart, chartIndex) => {
    const chart = asObject(rawChart) ?? {};
    const rows = Array.isArray(chart.data) ? chart.data.map(asObject).filter(Boolean) as Array<Record<string, unknown>> : [];
    const encoding = asObject(chart.encoding) ?? {};
    const yKey = String(encoding.y ?? "count");
    const xKey = String(encoding.x ?? ("category" in (rows[0] ?? {}) ? "category" : "bin"));
    const maximum = Math.max(...rows.map((row) => Number(row[yKey] ?? 0)), 1);
    return <section className="artifact-chart" key={String(chart.chart_id ?? chartIndex)}><h3>{String(chart.title ?? "分析图表")}</h3><div className="bar-chart">{rows.slice(0, 12).map((row, index) => { const value = Number(row[yKey] ?? 0); return <div key={`${String(row[xKey])}-${index}`}><span title={String(row[xKey] ?? index + 1)}>{String(row[xKey] ?? index + 1)}</span><i style={{ width: `${Math.max(2, value / maximum * 100)}%` }} /><b>{formatValue(value)}</b></div>; })}</div></section>;
  })}</div>;
}

function TableArtifact({ artifact }: { artifact: Artifact }) {
  const result = asObject(artifact.result) ?? {};
  const rows = Array.isArray(result.rows) ? result.rows.map(asObject).filter(Boolean) as Array<Record<string, unknown>> : [];
  const columns = Array.isArray(result.columns) ? result.columns.map(String) : Object.keys(rows[0] ?? {});
  if (!rows.length) return <pre>{JSON.stringify(artifact.result, null, 2)}</pre>;
  return <div className="artifact-table-wrap"><table><thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.slice(0, 30).map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{formatValue(row[column])}</td>)}</tr>)}</tbody></table></div>;
}

export function ArtifactViewer({ artifacts }: { artifacts: Artifact[] }) {
  const { project } = useAppContext();
  const { pushToast } = useToast();
  const types = useMemo(() => [...new Set(artifacts.map((item) => item.type))], [artifacts]);
  const [type, setType] = useState<Artifact["type"]>("metric");
  const selectedType = types.includes(type) ? type : types[0];
  const selected = artifacts.find((item) => item.type === selectedType);
  const labels: Record<Artifact["type"], string> = { metric: "指标", chart: "图表", table: "表格", model: "模型", file: "文件", log: "日志", comparison: "比较" };
  return <section className="artifact-viewer"><nav>{types.map((item) => <button className={selectedType === item ? "is-active" : ""} key={item} onClick={() => setType(item)}>{labels[item]}</button>)}</nav>{selected ? <div className="artifact-content"><header><div><h2>{selected.name}</h2><p>{selected.artifact_id} · {selected.producer} {selected.producer_version}</p></div>{selected.downloadable && project ? <Button icon={<Download size={15} />} onClick={async () => { const download = await apiClient.downloadArtifact(project.project_id, selected.artifact_id); pushToast(`正在下载 ${download.file_name}`); }} size="sm">下载</Button> : null}</header>{selected.type === "chart" ? <ChartArtifact artifact={selected} /> : selected.type === "table" ? <TableArtifact artifact={selected} /> : selected.type === "metric" ? <MetricArtifact artifact={selected} /> : <pre>{JSON.stringify(selected.result, null, 2)}</pre>}</div> : <EmptyState title="暂无分析产物" description="运行完成后会在这里显示真实数据生成的可追溯产物。" />}</section>;
}
