import type {
  AnalysisSpec,
  AnalysisSpecInput,
  AnalysisRun,
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
    return createJob("report_export", `生成 ${input.format.toUpperCase()} 导出`, "report_export", `exp_${crypto.randomUUID().slice(0, 8)}`);
  },
};
