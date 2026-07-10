import { ApiError, toApiError } from "./errors";
import { mockApi } from "./mockApi";
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
  Download,
  ErrorDetail,
  Job,
  Page,
  Project,
  ProjectCreate,
  QualityIssue,
  ReportExportInput,
  SchemaPatch,
  SessionInfo,
} from "./contracts";
import { jobSchema, projectPageSchema, projectSchema } from "./validators";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";
const API_MODE = import.meta.env.VITE_API_MODE ?? "mock";
const TOKEN = import.meta.env.VITE_DEV_AUTH_TOKEN ?? "";

function idempotencyKey() {
  return crypto.randomUUID();
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  try {
    const headers = new Headers(init.headers);
    if (TOKEN) headers.set("Authorization", `Bearer ${TOKEN}`);
    if (!(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
    if (!response.ok) {
      const payload = (await response.json().catch(() => null)) as { error?: ErrorDetail } | null;
      throw new ApiError(
        response.status,
        payload?.error ?? {
          code: "HTTP_ERROR",
          message: `请求失败（${response.status}）`,
          request_id: response.headers.get("x-request-id") ?? "req_unknown",
          retryable: response.status >= 500,
          details: {},
        },
      );
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    throw toApiError(error);
  }
}

export const apiClient = {
  mode: API_MODE,

  login(username: string, password: string): Promise<SessionInfo> {
    if (API_MODE === "mock") return mockApi.login(username);
    return request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  getSession(): Promise<SessionInfo> {
    if (API_MODE === "mock") return mockApi.getSession();
    return request("/auth/session");
  },

  logout(): Promise<void> {
    if (API_MODE === "mock") return mockApi.logout();
    return request("/auth/logout", { method: "POST" });
  },

  listProjects(): Promise<Page<Project>> {
    if (API_MODE === "mock") return mockApi.listProjects().then((value) => projectPageSchema.parse(value));
    return request<unknown>("/projects?page=1&page_size=20&status=active").then((value) => projectPageSchema.parse(value));
  },

  createProject(input: ProjectCreate): Promise<Project> {
    if (API_MODE === "mock") return mockApi.createProject(input).then((value) => projectSchema.parse(value));
    return request<unknown>("/projects", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify(input),
    }).then((value) => projectSchema.parse(value));
  },

  listDatasets(projectId: string): Promise<Page<Dataset>> {
    if (API_MODE === "mock") return mockApi.listDatasets(projectId);
    return request(`/projects/${projectId}/datasets?page=1&page_size=20`);
  },

  uploadDataset(projectId: string, file: File, datasetName: string): Promise<Job> {
    if (API_MODE === "mock") return mockApi.uploadDataset(projectId, file, datasetName).then((value) => jobSchema.parse(value));
    const body = new FormData();
    body.append("file", file);
    body.append("dataset_name", datasetName);
    return request<unknown>(`/projects/${projectId}/datasets`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey() },
      body,
    }).then((value) => jobSchema.parse(value));
  },

  listDatasetVersions(projectId: string, datasetId: string): Promise<Page<DatasetVersion>> {
    if (API_MODE === "mock") return mockApi.listDatasetVersions(datasetId);
    return request(`/projects/${projectId}/datasets/${datasetId}/versions?page=1&page_size=20`);
  },

  previewDatasetVersion(projectId: string, datasetId: string, versionId: string): Promise<DataPreview> {
    if (API_MODE === "mock") return mockApi.previewDatasetVersion();
    return request(`/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/preview?limit=50`);
  },

  getDatasetSchema(projectId: string, versionId: string): Promise<DatasetSchema> {
    if (API_MODE === "mock") return mockApi.getDatasetSchema(versionId);
    return request(`/projects/${projectId}/dataset-versions/${versionId}/schema`);
  },

  updateDatasetSchema(projectId: string, versionId: string, revision: number, patch: SchemaPatch) {
    if (API_MODE === "mock") return mockApi.updateDatasetSchema(projectId, versionId, patch);
    return request<DatasetSchema>(`/projects/${projectId}/dataset-versions/${versionId}/schema`, {
      method: "PATCH",
      headers: { "If-Match": `"${revision}"` },
      body: JSON.stringify(patch),
    });
  },

  createQualityScan(projectId: string, versionId: string): Promise<Job> {
    if (API_MODE === "mock") return mockApi.createQualityScan().then((value) => jobSchema.parse(value));
    return request<unknown>(`/projects/${projectId}/dataset-versions/${versionId}/quality-scans`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify({ force: false, rules: [] }),
    }).then((value) => jobSchema.parse(value));
  },

  listQualityIssues(projectId: string, versionId: string): Promise<Page<QualityIssue>> {
    if (API_MODE === "mock") return mockApi.listQualityIssues(versionId);
    return request(`/projects/${projectId}/dataset-versions/${versionId}/quality-issues?page=1&page_size=20`);
  },

  updateQualityIssue(
    projectId: string,
    issue: QualityIssue,
    status: "open" | "accepted" | "ignored",
    reason: string | null,
  ): Promise<QualityIssue> {
    if (API_MODE === "mock") return mockApi.updateQualityIssue(projectId, issue.issue_id, status, reason);
    return request(`/projects/${projectId}/quality-issues/${issue.issue_id}`, {
      method: "PATCH",
      headers: { "If-Match": `"${issue.revision}"` },
      body: JSON.stringify({ status, reason }),
    });
  },

  getJob(jobId: string): Promise<Job> {
    if (API_MODE === "mock") return mockApi.getJob(jobId).then((value) => jobSchema.parse(value));
    return request<unknown>(`/jobs/${jobId}`).then((value) => jobSchema.parse(value));
  },

  cancelJob(jobId: string): Promise<Job> {
    if (API_MODE === "mock") return mockApi.cancelJob(jobId).then((value) => jobSchema.parse(value));
    return request<unknown>(`/jobs/${jobId}/cancel`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey() },
    }).then((value) => jobSchema.parse(value));
  },

  listRuns(projectId: string): Promise<Page<AnalysisRun>> {
    if (API_MODE === "mock") return mockApi.listRuns();
    return request(`/projects/${projectId}/runs?page=1&page_size=20`);
  },

  listArtifacts(projectId: string, runId: string): Promise<Page<Artifact>> {
    if (API_MODE === "mock") return mockApi.listArtifacts();
    return request(`/projects/${projectId}/runs/${runId}/artifacts?page=1&page_size=20`);
  },

  getArtifact(projectId: string, artifactId: string): Promise<Artifact> {
    if (API_MODE === "mock") return mockApi.getArtifact(artifactId);
    return request(`/projects/${projectId}/artifacts/${artifactId}`);
  },

  createArtifactDownload(projectId: string, artifactId: string): Promise<Download> {
    if (API_MODE === "mock") return mockApi.createArtifactDownload(artifactId);
    return request<Download>(`/projects/${projectId}/artifacts/${artifactId}/download`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
    });
  },

  async downloadArtifact(projectId: string, artifactId: string): Promise<Download> {
    const download = await this.createArtifactDownload(projectId, artifactId);
    const anchor = document.createElement("a");
    anchor.href = download.download_url;
    anchor.download = download.file_name;
    anchor.rel = "noopener";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    return download;
  },

  listCleaningPlans(projectId: string, versionId: string): Promise<Page<CleaningPlan>> {
    if (API_MODE === "mock") return mockApi.listCleaningPlans();
    return request(`/projects/${projectId}/cleaning-plans?source_version_id=${versionId}`);
  },

  createCleaningPlan(projectId: string, versionId: string, operations: CleaningOperation[]): Promise<CleaningPlan> {
    if (API_MODE === "mock") return mockApi.createCleaningPlan(projectId, versionId, operations);
    return request(`/projects/${projectId}/cleaning-plans`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify({ source_version_id: versionId, name: "数据质量修复", operations }),
    });
  },

  updateCleaningPlan(projectId: string, plan: CleaningPlan, name: string, operations: CleaningOperation[]): Promise<CleaningPlan> {
    if (API_MODE === "mock") return mockApi.updateCleaningPlan(plan.plan_id, name, operations);
    return request(`/projects/${projectId}/cleaning-plans/${plan.plan_id}`, {
      method: "PATCH", headers: { "If-Match": `"${plan.revision}"` },
      body: JSON.stringify({ name, operations }),
    });
  },

  previewCleaningPlan(projectId: string, planId: string): Promise<Job> {
    if (API_MODE === "mock") return mockApi.previewCleaningPlan(planId);
    return request(`/projects/${projectId}/cleaning-plans/${planId}/preview`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
    });
  },

  decideCleaningPlan(projectId: string, planId: string, decision: "approve" | "reject", reason: string | null): Promise<CleaningPlan> {
    if (API_MODE === "mock") return mockApi.decideCleaningPlan(planId, decision, reason);
    return request(`/projects/${projectId}/cleaning-plans/${planId}/decision`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify({ decision, reason }),
    });
  },

  executeCleaningPlan(projectId: string, planId: string): Promise<Job> {
    if (API_MODE === "mock") return mockApi.executeCleaningPlan(planId);
    return request(`/projects/${projectId}/cleaning-plans/${planId}/execute`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
    });
  },

  async activateDatasetVersion(
    projectId: string,
    datasetId: string,
    versionId: string,
  ): Promise<DatasetVersion> {
    if (API_MODE === "mock") return mockApi.activateDatasetVersion(datasetId, versionId);
    await request<Dataset>(`/projects/${projectId}/datasets/${datasetId}/versions/${versionId}/activate`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
    });
    const versions = await this.listDatasetVersions(projectId, datasetId);
    const activated = versions.items.find((item) => item.version_id === versionId);
    if (!activated) {
      throw new ApiError(500, {
        code: "CLIENT_CONTRACT_ERROR",
        message: "版本已激活，但版本列表未返回目标版本",
        request_id: "req_client",
        retryable: true,
        details: { version_id: versionId },
      });
    }
    return activated;
  },

  compareDatasetVersions(
    projectId: string,
    datasetId: string,
    baseVersionId: string,
    compareVersionId: string,
  ): Promise<Job> {
    if (API_MODE === "mock") return mockApi.compareDatasetVersions();
    return request(`/projects/${projectId}/datasets/${datasetId}/version-comparisons`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify({ base_version_id: baseVersionId, compare_version_id: compareVersionId }),
    });
  },

  listAnalysisSpecs(projectId: string, versionId: string): Promise<Page<AnalysisSpec>> {
    if (API_MODE === "mock") return mockApi.listAnalysisSpecs();
    return request(`/projects/${projectId}/analysis-specs?dataset_version_id=${versionId}`);
  },

  createAnalysisSpec(projectId: string, input: AnalysisSpecInput): Promise<AnalysisSpec> {
    if (API_MODE === "mock") return mockApi.createAnalysisSpec(projectId, input);
    return request(`/projects/${projectId}/analysis-specs`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify(input),
    });
  },

  updateAnalysisSpec(projectId: string, spec: AnalysisSpec, input: AnalysisSpecInput): Promise<AnalysisSpec> {
    if (API_MODE === "mock") return mockApi.updateAnalysisSpec(spec.spec_id, input);
    return request(`/projects/${projectId}/analysis-specs/${spec.spec_id}`, {
      method: "PATCH", headers: { "If-Match": `"${spec.revision}"` }, body: JSON.stringify(input),
    });
  },

  confirmAnalysisSpec(projectId: string, specId: string): Promise<AnalysisSpec> {
    if (API_MODE === "mock") return mockApi.confirmAnalysisSpec(specId);
    return request(`/projects/${projectId}/analysis-specs/${specId}/confirm`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
    });
  },

  createRun(projectId: string, specId: string, versionId: string): Promise<Job> {
    if (API_MODE === "mock") return mockApi.createRun(projectId, specId, versionId);
    return request(`/projects/${projectId}/runs`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
      body: JSON.stringify({ analysis_spec_id: specId, dataset_version_id: versionId, run_kind: "full" }),
    });
  },

  getRun(projectId: string, runId: string): Promise<AnalysisRun> {
    if (API_MODE === "mock") return mockApi.getRun(runId);
    return request(`/projects/${projectId}/runs/${runId}`);
  },

  cancelRun(projectId: string, runId: string): Promise<AnalysisRun> {
    if (API_MODE === "mock") return mockApi.cancelRun(runId);
    return request(`/projects/${projectId}/runs/${runId}/cancel`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() },
    });
  },

  listClaims(projectId: string, runId: string): Promise<Page<Claim>> {
    if (API_MODE === "mock") return mockApi.listClaims();
    return request(`/projects/${projectId}/runs/${runId}/claims?page=1&page_size=20`);
  },

  getClaim(projectId: string, claimId: string): Promise<Claim> {
    if (API_MODE === "mock") return mockApi.getClaim(claimId);
    return request(`/projects/${projectId}/claims/${claimId}`);
  },

  createReportExport(projectId: string, input: ReportExportInput): Promise<Job> {
    if (API_MODE === "mock") return mockApi.createReportExport(input);
    return request(`/projects/${projectId}/reports`, {
      method: "POST", headers: { "Idempotency-Key": idempotencyKey() }, body: JSON.stringify(input),
    });
  },
};
