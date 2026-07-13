export const queryKeys = {
  projects: ["projects"] as const,
  datasets: (projectId: string) => ["projects", projectId, "datasets"] as const,
  versions: (projectId: string, datasetId: string) =>
    ["projects", projectId, "datasets", datasetId, "versions"] as const,
  preview: (projectId: string, datasetId: string, versionId: string) =>
    ["projects", projectId, "datasets", datasetId, "versions", versionId, "preview"] as const,
  schema: (projectId: string, versionId: string) =>
    ["projects", projectId, "versions", versionId, "schema"] as const,
  qualityIssues: (projectId: string, versionId: string) =>
    ["projects", projectId, "versions", versionId, "quality-issues"] as const,
  job: (jobId: string) => ["jobs", jobId] as const,
  runs: (projectId: string) => ["projects", projectId, "runs"] as const,
  artifacts: (projectId: string, runId: string) =>
    ["projects", projectId, "runs", runId, "artifacts"] as const,
  cleaningPlans: (projectId: string, versionId: string) =>
    ["projects", projectId, "versions", versionId, "cleaning-plans"] as const,
  analysisSpecs: (projectId: string, versionId: string) =>
    ["projects", projectId, "versions", versionId, "analysis-specs"] as const,
  claims: (projectId: string, runId: string) =>
    ["projects", projectId, "runs", runId, "claims"] as const,
  assistantConversations: (projectId: string) =>
    ["projects", projectId, "assistant", "conversations"] as const,
  assistantMessages: (projectId: string, conversationId: string) =>
    ["projects", projectId, "assistant", "conversations", conversationId, "messages"] as const,
};
