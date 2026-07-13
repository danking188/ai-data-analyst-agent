import type {
  AnalysisSpec,
  AnalysisSpecInput,
  AnalysisRun,
  AssistantConversation,
  AssistantFeedback,
  AssistantMessage,
  AssistantMetrics,
  AssistantTurnAccepted,
  Artifact,
  Claim,
  CleaningOperation,
  CleaningPlan,
  DataPreview,
  Dataset,
  DatasetSchema,
  DatasetVersion,
  Job,
  Page,
  Project,
  ProjectCreate,
  QualityIssue,
  ReportExportInput,
  SchemaPatch,
  SystemCapabilities,
} from "./contracts";
import {
  seedAnalysisSpec,
  seedArtifacts,
  seedClaims,
  seedCleaningPlan,
  seedColumns,
  seedDataset,
  seedIssues,
  seedProject,
  seedRows,
  seedRuns,
  seedVersions,
} from "./mockData";

const wait = (ms = 220) => new Promise((resolve) => window.setTimeout(resolve, ms));
const projects = [structuredClone(seedProject)];
const issues = structuredClone(seedIssues);
const schemas: DatasetSchema = {
  dataset_version_id: "dsv_03JABC",
  revision: 4,
  low_confidence_count: 2,
  columns: structuredClone(seedColumns),
};
const jobs = new Map<string, Job>();
const jobStarted = new Map<string, number>();
const cleaningPlans = [structuredClone(seedCleaningPlan)];
const analysisSpecs = [structuredClone(seedAnalysisSpec)];
const runs = structuredClone(seedRuns);
const artifacts = structuredClone(seedArtifacts);
const claims = structuredClone(seedClaims);
const assistantNow = new Date().toISOString();
const assistantConversations: AssistantConversation[] = [
  {
    conversation_id: "conv_demo_sales",
    project_id: seedProject.project_id,
    title: "客户流失与数据质量",
    status: "active",
    dataset_version_id: seedVersions[0]?.version_id ?? null,
    created_by: "demo-analyst",
    created_at: assistantNow,
    updated_at: assistantNow,
    archived_at: null,
  },
];
const assistantMessages = new Map<string, AssistantMessage[]>([
  [
    "conv_demo_sales",
    [
      {
        message_id: "msg_demo_user_1",
        conversation_id: "conv_demo_sales",
        role: "user",
        status: "completed",
        content: "总结当前分析里最值得关注的结论。",
        plan: null,
        answer: null,
        tool_calls: [],
        parent_message_id: null,
        job_id: null,
        created_at: assistantNow,
        completed_at: assistantNow,
      },
      {
        message_id: "msg_demo_assistant_1",
        conversation_id: "conv_demo_sales",
        role: "assistant",
        status: "completed",
        content: "现有证据显示客户流失与合同类型、服务时长有关，建议先处理数据质量问题，再确认建模规格。",
        plan: null,
        answer: {
          summary: "现有证据显示客户流失与合同类型、服务时长有关，建议先处理数据质量问题，再确认建模规格。",
          findings: seedClaims.slice(0, 2).map((claim) => ({
            text: claim.text,
            claim_level: claim.level,
            citation_ids: [claim.claim_id],
            limitations: claim.limitations,
          })),
          next_actions: [
            { label: "草拟分类分析规格", action_type: "draft_spec", requires_confirmation: true },
          ],
          limitations: ["当前结论来自关联分析，不代表因果关系。"],
        },
        tool_calls: [
          {
            tool_call_id: "tool_demo_claims",
            tool_name: "claim.search",
            tool_version: "1.0.0",
            status: "succeeded",
            requires_confirmation: false,
            arguments: {},
            result: { claim_count: 2 },
            result_resource_type: null,
            result_resource_id: null,
          },
        ],
        parent_message_id: "msg_demo_user_1",
        job_id: "job_demo_assistant_1",
        created_at: assistantNow,
        completed_at: assistantNow,
      },
      {
        message_id: "msg_demo_user_2",
        conversation_id: "conv_demo_sales",
        role: "user",
        status: "completed",
        content: "为流失预测准备一个新的分类分析。",
        plan: null,
        answer: null,
        tool_calls: [],
        parent_message_id: null,
        job_id: null,
        created_at: assistantNow,
        completed_at: assistantNow,
      },
      {
        message_id: "msg_demo_assistant_plan",
        conversation_id: "conv_demo_sales",
        role: "assistant",
        status: "awaiting_confirmation",
        content: "已生成执行计划，确认前不会运行任何分析或数据变更。",
        plan: {
          objective: "建立可复现的客户流失分类分析",
          dataset_version_id: seedVersions[0]?.version_id ?? null,
          steps: [
            {
              position: 1,
              title: "草拟分析规格",
              tool_name: "analysis.draft_spec",
              purpose: "确认目标列、特征边界、数据切分和评价指标",
              requires_confirmation: true,
            },
            {
              position: 2,
              title: "运行分类基线",
              tool_name: "analysis.run",
              purpose: "训练并比较可复现的候选模型",
              requires_confirmation: true,
            },
          ],
          estimated_model_calls: 2,
          estimated_tool_calls: 2,
          limitations: ["执行前需要确认目标列和时间边界。"],
        },
        answer: null,
        tool_calls: [
          {
            tool_call_id: "tool_demo_spec",
            tool_name: "analysis.draft_spec",
            tool_version: "1.0.0",
            status: "proposed",
            requires_confirmation: true,
            arguments: {
              name: "客户流失分类分析",
              task: "binary_classification",
              target: "churned",
              entity_key: "customer_id",
              time_column: null,
              prediction_time_description: "使用观察期结束前已知字段预测下一周期流失",
              split_strategy: "stratified",
              group_column: null,
              metrics: ["f1", "roc_auc", "pr_auc"],
              included_columns: ["tenure_months", "contract_type", "failed_payments_90d"],
              excluded_columns: ["customer_id", "cancel_date"],
              random_seed: 42,
              rationale: "目标是二元类别，使用分层拆分并排除事后字段。",
              leakage_warnings: ["cancel_date 发生在预测时点之后，必须排除。"],
              validation_warnings: [],
            },
            result: null,
            result_resource_type: null,
            result_resource_id: null,
          },
          {
            tool_call_id: "tool_demo_run",
            tool_name: "analysis.run",
            tool_version: "1.0.0",
            status: "proposed",
            requires_confirmation: true,
            arguments: { run_kind: "full" },
            result: null,
            result_resource_type: null,
            result_resource_id: null,
          },
        ],
        parent_message_id: "msg_demo_user_2",
        job_id: "job_demo_assistant_plan",
        created_at: assistantNow,
        completed_at: null,
      },
    ],
  ],
]);
const assistantFeedback: AssistantFeedback[] = [];

function page<T>(items: T[]): Page<T> {
  return { items, page: 1, page_size: 20, total: items.length, has_more: false };
}

function createJob(kind: Job["kind"], currentStep: string, resourceType: string | null = null, resourceId: string | null = null): Job {
  const jobId = `job_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  const timestamp = new Date().toISOString();
  const job: Job = {
    job_id: jobId,
    kind,
    status: "queued",
    progress: 0,
    current_step: currentStep,
    resource_type: resourceType,
    resource_id: resourceId,
    retry_after_ms: 600,
    created_at: timestamp,
    updated_at: timestamp,
    error: null,
  };
  jobs.set(jobId, job);
  jobStarted.set(jobId, Date.now());
  return structuredClone(job);
}

export const mockApi = {
  async getCapabilities(): Promise<SystemCapabilities> {
    await wait(20);
    return {
      api_version: "v1",
      supported_file_types: ["csv", "xls", "xlsx", "parquet"],
      max_upload_bytes: 524_288_000,
      natural_language_analysis: true,
      llm: {
        evidence_narrative: true,
        assistant: true,
      },
      auth_enabled: true,
      polling: {
        initial_interval_ms: 1000,
        steady_interval_ms: 3000,
        background_interval_ms: 10000,
      },
    };
  },

  async login(username: string) {
    await wait();
    return { subject_id: username, expires_in_seconds: 43_200 };
  },

  async register(username: string) {
    await wait();
    return { subject_id: username.trim().toLowerCase(), expires_in_seconds: 43_200 };
  },

  async getSession() {
    await wait(20);
    return { subject_id: "demo-analyst", expires_in_seconds: null };
  },

  async logout(): Promise<void> {
    await wait(20);
  },

  async listProjects(): Promise<Page<Project>> {
    await wait();
    return page(structuredClone(projects));
  },

  async createProject(input: ProjectCreate): Promise<Project> {
    await wait(380);
    const timestamp = new Date().toISOString();
    const project: Project = {
      project_id: `prj_${crypto.randomUUID().replaceAll("-", "").slice(0, 10)}`,
      name: input.name,
      description: input.description ?? null,
      timezone: input.timezone,
      language: input.language,
      status: "active",
      current_dataset_version_id: null,
      revision: 1,
      created_at: timestamp,
      updated_at: timestamp,
    };
    projects.unshift(project);
    return structuredClone(project);
  },

  async listDatasets(projectId: string): Promise<Page<Dataset>> {
    await wait();
    return page(projectId === seedProject.project_id ? [structuredClone(seedDataset)] : []);
  },

  async uploadDataset(_projectId: string, file: File, _datasetName: string): Promise<Job> {
    await wait(350);
    if (file.size > 524_288_000) throw new Error("文件超过 500 MiB 限制");
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!extension || !["csv", "xls", "xlsx", "parquet"].includes(extension)) {
      throw new Error("仅支持 CSV、XLS、XLSX 和 Parquet");
    }
    return createJob("dataset_ingestion", "安全校验与文件哈希");
  },

  async listDatasetVersions(datasetId: string): Promise<Page<DatasetVersion>> {
    await wait();
    return page(datasetId === seedDataset.dataset_id ? structuredClone(seedVersions) : []);
  },

  async previewDatasetVersion(): Promise<DataPreview> {
    await wait();
    return {
      columns: seedColumns.map((column) => ({
        name: column.name,
        physical_type: column.physical_type,
        semantic_type: column.semantic_type,
        masked: column.sensitive,
      })),
      rows: structuredClone(seedRows),
      next_cursor: "cursor_page_2",
      has_more: true,
      masked_columns: ["customer_id", "income"],
    };
  },

  async getDatasetSchema(versionId: string): Promise<DatasetSchema> {
    await wait();
    return { ...structuredClone(schemas), dataset_version_id: versionId };
  },

  async updateDatasetSchema(_projectId: string, _versionId: string, patch: SchemaPatch): Promise<DatasetSchema> {
    await wait(320);
    for (const change of patch.changes) {
      const column = schemas.columns.find((item) => item.name === change.column);
      if (!column) continue;
      if (change.semantic_type) column.semantic_type = change.semantic_type;
      if (change.analysis_role) column.analysis_role = change.analysis_role;
      if (typeof change.sensitive === "boolean") column.sensitive = change.sensitive;
      column.user_confirmed = true;
    }
    schemas.revision += 1;
    schemas.low_confidence_count = schemas.columns.filter((item) => !item.user_confirmed).length;
    return { ...structuredClone(schemas), dataset_version_id: _versionId };
  },

  async createQualityScan(): Promise<Job> {
    await wait(260);
    return createJob("quality_scan", "字段画像与质量规则");
  },

  async listQualityIssues(versionId: string): Promise<Page<QualityIssue>> {
    await wait();
    return page(structuredClone(issues).map((issue) => ({ ...issue, dataset_version_id: versionId })));
  },

  async updateQualityIssue(
    _projectId: string,
    issueId: string,
    status: "open" | "accepted" | "ignored",
    reason: string | null,
  ): Promise<QualityIssue> {
    await wait(280);
    const issue = issues.find((item) => item.issue_id === issueId);
    if (!issue) throw new Error("质量问题不存在");
    issue.status = status;
    issue.decision_reason = reason;
    issue.revision += 1;
    return structuredClone(issue);
  },

  async getJob(jobId: string): Promise<Job> {
    await wait(120);
    const job = jobs.get(jobId);
    if (!job) throw new Error("任务不存在");
    const elapsed = Date.now() - (jobStarted.get(jobId) ?? Date.now());
    if (job.status !== "cancelled") {
      if (elapsed < 900) {
        job.status = "running";
        job.progress = 28;
      } else if (elapsed < 1800) {
        job.status = "running";
        job.progress = 72;
        job.current_step = job.kind === "dataset_ingestion" ? "转换为内部 Parquet" : "汇总质量问题";
      } else {
        job.status = "succeeded";
        job.progress = 100;
        job.current_step = null;
        job.resource_type ??= job.kind === "dataset_ingestion" ? "dataset_version" : "quality_scan";
        job.resource_id ??= job.kind === "dataset_ingestion" ? "dsv_04JABC" : "scan_01JABC";
      }
      job.updated_at = new Date().toISOString();
    }
    return structuredClone(job);
  },

  async cancelJob(jobId: string): Promise<Job> {
    await wait(180);
    const job = jobs.get(jobId);
    if (!job) throw new Error("任务不存在");
    job.status = "cancelled";
    job.progress = Math.min(job.progress, 99);
    job.current_step = null;
    job.updated_at = new Date().toISOString();
    return structuredClone(job);
  },

  async listRuns() {
    await wait();
    return page(structuredClone(runs));
  },

  async listArtifacts() {
    await wait();
    return page(structuredClone(artifacts));
  },

  async getArtifact(artifactId: string): Promise<Artifact> {
    await wait();
    const artifact = artifacts.find((item) => item.artifact_id === artifactId);
    if (!artifact) throw new Error("Artifact 不存在");
    return structuredClone(artifact);
  },

  async createArtifactDownload(artifactId: string) {
    await wait();
    const artifact = artifacts.find((item) => item.artifact_id === artifactId);
    if (!artifact) throw new Error("Artifact 不存在");
    return {
      download_url: `https://downloads.example.test/${artifactId}`,
      file_name: `${artifact.name}.json`,
      content_type: "application/json",
      expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
    };
  },

  async listCleaningPlans(): Promise<Page<CleaningPlan>> {
    await wait();
    return page(structuredClone(cleaningPlans));
  },

  async createCleaningPlan(projectId: string, versionId: string, operations: CleaningOperation[]): Promise<CleaningPlan> {
    await wait();
    const timestamp = new Date().toISOString();
    const plan: CleaningPlan = {
      ...structuredClone(seedCleaningPlan),
      plan_id: `cln_${crypto.randomUUID().slice(0, 8)}`,
      project_id: projectId,
      source_version_id: versionId,
      operations,
      created_at: timestamp,
      updated_at: timestamp,
    };
    cleaningPlans.unshift(plan);
    return structuredClone(plan);
  },

  async updateCleaningPlan(planId: string, name: string, operations: CleaningOperation[]): Promise<CleaningPlan> {
    await wait();
    const plan = cleaningPlans.find((item) => item.plan_id === planId);
    if (!plan || plan.status !== "draft") throw new Error("只有草稿计划可以编辑");
    plan.name = name;
    plan.operations = structuredClone(operations);
    plan.revision += 1;
    plan.updated_at = new Date().toISOString();
    return structuredClone(plan);
  },

  async previewCleaningPlan(planId: string): Promise<Job> {
    await wait();
    const plan = cleaningPlans.find((item) => item.plan_id === planId);
    if (!plan) throw new Error("清洗计划不存在");
    plan.status = "awaiting_approval";
    plan.preview_artifact_id = "art_preview_cleaning";
    plan.revision += 1;
    const existing = artifacts.find((item) => item.artifact_id === plan.preview_artifact_id);
    if (!existing) {
      artifacts.unshift({
        artifact_id: plan.preview_artifact_id,
        project_id: plan.project_id,
        run_id: null,
        dataset_version_id: plan.source_version_id,
        type: "table",
        name: "清洗影响预览",
        producer: "cleaning.preview",
        producer_version: "1.0.0",
        status: "ready",
        parameters: { cleaning_plan_id: plan.plan_id },
        result: {
          cleaning_plan_id: plan.plan_id,
          source_version_id: plan.source_version_id,
          row_count_before: 82310,
          row_count_after: 82298,
          column_count_before: seedColumns.length,
          column_count_after: seedColumns.length + 1,
          operations: plan.operations.map((operation) => ({
            operation_id: operation.operation_id,
            operation: operation.operation,
            affected_rows: operation.estimated_affected_rows,
            row_count_before: 82310,
            row_count_after: operation.operation === "drop_duplicates" ? 82298 : 82310,
          })),
          sample_before: seedRows.slice(0, 3),
          sample_after: seedRows.slice(0, 3).map((row) => ({ ...row, income_was_missing: false })),
        },
        preview: null,
        checksum: `sha256:${"c".repeat(64)}`,
        downloadable: false,
        created_at: new Date().toISOString(),
      });
    }
    return createJob("cleaning_preview", "计算确定性影响预览", "cleaning_plan", planId);
  },

  async decideCleaningPlan(planId: string, decision: "approve" | "reject", reason: string | null): Promise<CleaningPlan> {
    await wait();
    const plan = cleaningPlans.find((item) => item.plan_id === planId);
    if (!plan?.preview_artifact_id) throw new Error("必须先生成预览");
    plan.decision = decision;
    plan.decision_reason = reason;
    plan.status = decision === "approve" ? "approved" : "rejected";
    plan.revision += 1;
    return structuredClone(plan);
  },

  async executeCleaningPlan(planId: string): Promise<Job> {
    await wait();
    const plan = cleaningPlans.find((item) => item.plan_id === planId);
    if (!plan || plan.status !== "approved") throw new Error("必须先批准计划");
    plan.status = "executing";
    plan.result_version_id = "dsv_04JABC";
    return createJob("cleaning_execute", "生成不可变清洗版本", "dataset_version", "dsv_04JABC");
  },

  async activateDatasetVersion(_datasetId: string, versionId: string): Promise<DatasetVersion> {
    await wait();
    const version = seedVersions.find((item) => item.version_id === versionId) ?? {
      ...seedVersions[0]!,
      version_id: versionId,
      version_number: 4,
      parent_version_id: "dsv_03JABC",
      operation_summary: "执行客户数据质量修复",
    };
    return structuredClone(version);
  },

  async compareDatasetVersions(): Promise<Job> {
    await wait();
    return createJob("version_comparison", "计算版本差异", "artifact", "art_version_compare");
  },

  async listAnalysisSpecs(): Promise<Page<AnalysisSpec>> {
    await wait();
    return page(structuredClone(analysisSpecs));
  },

  async createAnalysisSpec(projectId: string, input: AnalysisSpecInput): Promise<AnalysisSpec> {
    await wait();
    const timestamp = new Date().toISOString();
    const spec: AnalysisSpec = {
      ...structuredClone(input),
      spec_id: `spec_${crypto.randomUUID().slice(0, 8)}`,
      project_id: projectId,
      revision: 1,
      status: "draft",
      validation_warnings: input.excluded_columns.includes("cancel_date") ? [] : ["建议排除预测时点后生成的 cancel_date。"],
      created_at: timestamp,
      updated_at: timestamp,
    };
    analysisSpecs.unshift(spec);
    return structuredClone(spec);
  },

  async updateAnalysisSpec(specId: string, input: AnalysisSpecInput): Promise<AnalysisSpec> {
    await wait();
    const spec = analysisSpecs.find((item) => item.spec_id === specId);
    if (!spec || spec.status !== "draft") throw new Error("只有草稿 AnalysisSpec 可以编辑");
    Object.assign(spec, structuredClone(input), { revision: spec.revision + 1, updated_at: new Date().toISOString() });
    return structuredClone(spec);
  },

  async confirmAnalysisSpec(specId: string): Promise<AnalysisSpec> {
    await wait();
    const spec = analysisSpecs.find((item) => item.spec_id === specId);
    if (!spec) throw new Error("AnalysisSpec 不存在");
    spec.status = "confirmed";
    spec.revision += 1;
    return structuredClone(spec);
  },

  async createRun(projectId: string, specId: string, versionId: string): Promise<Job> {
    await wait();
    const spec = analysisSpecs.find((item) => item.spec_id === specId);
    if (!spec || spec.status !== "confirmed") throw new Error("必须先确认 AnalysisSpec");
    const runId = `run_${crypto.randomUUID().slice(0, 8)}`;
    const run: AnalysisRun = {
      ...structuredClone(seedRuns[1]!),
      run_id: runId,
      project_id: projectId,
      dataset_version_id: versionId,
      analysis_spec_id: specId,
      status: "running",
      progress: 12,
      created_at: new Date().toISOString(),
    };
    runs.unshift(run);
    return createJob("analysis_run", "数据准备", "analysis_run", runId);
  },

  async getRun(runId: string): Promise<AnalysisRun> {
    await wait();
    const run = runs.find((item) => item.run_id === runId);
    if (!run) throw new Error("分析运行不存在");
    return structuredClone(run);
  },

  async cancelRun(runId: string): Promise<AnalysisRun> {
    await wait();
    const run = runs.find((item) => item.run_id === runId);
    if (!run) throw new Error("分析运行不存在");
    run.status = "cancelled";
    run.steps = run.steps.map((item) => item.status === "running" ? { ...item, status: "cancelled" } : item);
    return structuredClone(run);
  },

  async listClaims(): Promise<Page<Claim>> {
    await wait();
    return page(structuredClone(claims));
  },

  async getClaim(claimId: string): Promise<Claim> {
    await wait();
    const claim = claims.find((item) => item.claim_id === claimId);
    if (!claim) throw new Error("Claim 不存在");
    return structuredClone(claim);
  },

  async createReportExport(input: ReportExportInput): Promise<Job> {
    await wait();
    if (input.format === "ai_narrative") {
      const artifactId = `art_ai_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`;
      artifacts.push({
        artifact_id: artifactId,
        project_id: seedProject.project_id,
        run_id: input.run_id,
        dataset_version_id: runs.find((run) => run.run_id === input.run_id)?.dataset_version_id ?? "dsv_03JABC",
        type: "log",
        name: "AI 证据解读",
        producer: "llm_report_narrative",
        producer_version: "1.0.0",
        status: "ready",
        parameters: {
          provider: "fake",
          model: "mock-analysis",
          prompt_name: "assistant.report_narrative",
          prompt_version: "1.0.0",
        },
        result: {
          summary: "当前分析已经形成可追溯的统计与模型证据。",
          findings: seedClaims.slice(0, 2).map((claim) => ({
            text: claim.text,
            claim_level: claim.level,
            citation_ids: [claim.claim_id],
            limitations: claim.limitations,
          })),
          next_actions: [],
          limitations: [...new Set(seedClaims.flatMap((claim) => claim.limitations))],
        },
        preview: null,
        checksum: `sha256:${"a".repeat(64)}`,
        downloadable: false,
        created_at: new Date().toISOString(),
      });
      return createJob("report_export", "生成 AI 证据解读", "artifact", artifactId);
    }
    return createJob("report_export", `生成 ${input.format.toUpperCase()} 导出`, "report_export", `exp_${crypto.randomUUID().slice(0, 8)}`);
  },

  async listAssistantConversations(projectId: string): Promise<Page<AssistantConversation>> {
    await wait();
    return page(structuredClone(assistantConversations.filter((item) => item.project_id === projectId)));
  },

  async getAssistantMetrics(projectId: string): Promise<AssistantMetrics> {
    await wait();
    const conversationIds = assistantConversations
      .filter((item) => item.project_id === projectId)
      .map((item) => item.conversation_id);
    const messages = conversationIds.flatMap((id) => assistantMessages.get(id) ?? []);
    const assistant = messages.filter((item) => item.role === "assistant");
    const calls = assistant.flatMap((item) => item.tool_calls);
    return {
      window_days: 7,
      turn_count: assistant.length,
      succeeded_count: assistant.filter((item) => item.status === "completed").length,
      failed_count: assistant.filter((item) => item.status === "failed").length,
      input_tokens: assistant.length * 820,
      output_tokens: assistant.length * 260,
      average_latency_ms: assistant.length ? 1840 : 0,
      p95_latency_ms: assistant.length ? 2600 : 0,
      tool_call_count: calls.length,
      tool_succeeded_count: calls.filter((item) => item.status === "succeeded").length,
      tool_failed_count: calls.filter((item) => item.status === "failed").length,
      tool_rejected_count: calls.filter((item) => item.status === "rejected").length,
    };
  },

  async createAssistantConversation(
    projectId: string,
    input: { title?: string | null; dataset_version_id?: string | null },
  ): Promise<AssistantConversation> {
    await wait();
    const timestamp = new Date().toISOString();
    const conversation: AssistantConversation = {
      conversation_id: `conv_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`,
      project_id: projectId,
      title: input.title || "新分析会话",
      status: "active",
      dataset_version_id: input.dataset_version_id ?? null,
      created_by: "demo-analyst",
      created_at: timestamp,
      updated_at: timestamp,
      archived_at: null,
    };
    assistantConversations.unshift(conversation);
    assistantMessages.set(conversation.conversation_id, []);
    return structuredClone(conversation);
  },

  async updateAssistantConversation(
    conversationId: string,
    input: { title?: string; status?: "active" | "archived"; dataset_version_id?: string | null },
  ): Promise<AssistantConversation> {
    await wait();
    const conversation = assistantConversations.find((item) => item.conversation_id === conversationId);
    if (!conversation) throw new Error("分析会话不存在");
    if (input.title !== undefined) conversation.title = input.title;
    if (input.status !== undefined) {
      conversation.status = input.status;
      conversation.archived_at = input.status === "archived" ? new Date().toISOString() : null;
    }
    if ("dataset_version_id" in input) conversation.dataset_version_id = input.dataset_version_id ?? null;
    conversation.updated_at = new Date().toISOString();
    return structuredClone(conversation);
  },

  async listAssistantMessages(conversationId: string): Promise<Page<AssistantMessage>> {
    await wait(80);
    return page(structuredClone(assistantMessages.get(conversationId) ?? []));
  },

  async createAssistantMessage(
    _projectId: string,
    conversationId: string,
    content: string,
  ): Promise<AssistantTurnAccepted> {
    await wait();
    const timestamp = new Date().toISOString();
    const userMessage: AssistantMessage = {
      message_id: `msg_${crypto.randomUUID().slice(0, 8)}`,
      conversation_id: conversationId,
      role: "user",
      status: "completed",
      content,
      plan: null,
      answer: null,
      tool_calls: [],
      parent_message_id: null,
      job_id: null,
      created_at: timestamp,
      completed_at: timestamp,
    };
    const job = createJob("assistant_turn", "读取项目证据");
    job.status = "succeeded";
    job.progress = 100;
    const assistantMessage: AssistantMessage = {
      message_id: `msg_${crypto.randomUUID().slice(0, 8)}`,
      conversation_id: conversationId,
      role: "assistant",
      status: "completed",
      content: "我已读取当前项目上下文。这个问题需要结合现有证据继续判断。",
      plan: null,
      answer: {
        summary: "我已读取当前项目上下文。这个问题需要结合现有证据继续判断。",
        findings: [],
        next_actions: [],
        limitations: ["Mock 模式未执行新的数据计算。"],
      },
      tool_calls: [
        {
          tool_call_id: `tool_${crypto.randomUUID().slice(0, 8)}`,
          tool_name: "project.get_context",
          tool_version: "1.0.0",
          status: "succeeded",
          requires_confirmation: false,
          arguments: {},
          result: { project_id: seedProject.project_id },
          result_resource_type: null,
          result_resource_id: null,
        },
      ],
      parent_message_id: userMessage.message_id,
      job_id: job.job_id,
      created_at: timestamp,
      completed_at: timestamp,
    };
    assistantMessages.get(conversationId)?.push(userMessage, assistantMessage);
    return { user_message: structuredClone(userMessage), assistant_message: structuredClone(assistantMessage), job };
  },

  async confirmAssistantPlan(
    messageId: string,
    decision: "approve" | "reject",
    toolCallIds: string[],
  ): Promise<AssistantTurnAccepted> {
    await wait();
    const message = [...assistantMessages.values()].flat().find((item) => item.message_id === messageId);
    if (!message) throw new Error("Assistant 消息不存在");
    const selected = toolCallIds.length ? new Set(toolCallIds) : null;
    message.tool_calls = message.tool_calls.map((call) =>
      !selected || selected.has(call.tool_call_id)
        ? { ...call, status: decision === "approve" ? "approved" : "rejected" }
        : call,
    );
    if (decision === "reject") {
      message.status = "completed";
      message.content = "计划已取消，未执行任何变更。";
      message.answer = { summary: message.content, findings: [], next_actions: [], limitations: [] };
      return { user_message: null, assistant_message: structuredClone(message), job: null };
    }
    message.status = "completed";
    message.content = "计划已确认，后续操作将由受控任务继续执行。";
    const continuation = await this.createAssistantMessage("", message.conversation_id, "执行已确认计划");
    return { ...continuation, user_message: null };
  },

  async updateAssistantToolCall(
    toolCallId: string,
    argumentsValue: Record<string, unknown>,
  ) {
    await wait();
    const call = [...assistantMessages.values()]
      .flat()
      .flatMap((message) => message.tool_calls)
      .find((item) => item.tool_call_id === toolCallId);
    if (!call || call.status !== "proposed") {
      throw new Error("只有待确认的工具调用可以编辑");
    }
    call.arguments = structuredClone(argumentsValue);
    return structuredClone(call);
  },

  async cancelAssistantMessage(messageId: string): Promise<AssistantMessage> {
    await wait();
    const message = [...assistantMessages.values()].flat().find((item) => item.message_id === messageId);
    if (!message) throw new Error("Assistant 消息不存在");
    message.status = "cancelled";
    return structuredClone(message);
  },

  async retryAssistantMessage(messageId: string): Promise<AssistantTurnAccepted> {
    await wait();
    const source = [...assistantMessages.values()].flat().find((item) => item.message_id === messageId);
    if (!source) throw new Error("Assistant 消息不存在");
    return this.createAssistantMessage("", source.conversation_id, "重试上一轮问题");
  },

  async createAssistantFeedback(
    messageId: string,
    rating: "helpful" | "not_helpful",
  ): Promise<AssistantFeedback> {
    await wait();
    const feedback: AssistantFeedback = {
      feedback_id: `fb_${crypto.randomUUID().slice(0, 8)}`,
      message_id: messageId,
      rating,
      reason: null,
      comment: null,
      created_at: new Date().toISOString(),
    };
    assistantFeedback.push(feedback);
    return structuredClone(feedback);
  },
};
