import { describe, expect, it } from "vitest";
import { mockApi } from "./mockApi";

describe("mockApi contract behavior", () => {
  it("returns the contract-shaped seeded project page", async () => {
    const result = await mockApi.listProjects();
    expect(result.page).toBe(1);
    expect(result.items[0]?.project_id).toMatch(/^prj_/);
    expect(result.items[0]?.status).toBe("active");
  });

  it("creates an upload job and moves it out of queued state", async () => {
    const file = new File(["customer_id,churn_30d\n1,0"], "churn.csv", { type: "text/csv" });
    const job = await mockApi.uploadDataset("prj_01JABC", file, "churn");
    const polled = await mockApi.getJob(job.job_id);
    expect(polled.kind).toBe("dataset_ingestion");
    expect(["running", "succeeded"]).toContain(polled.status);
  });

  it("keeps datasets isolated by project", async () => {
    const result = await mockApi.listDatasets("prj_unknown");
    expect(result.items).toEqual([]);
  });

  it("enforces cleaning preview before approval and execution", async () => {
    const plans = await mockApi.listCleaningPlans();
    const plan = plans.items[0]!;
    await expect(mockApi.decideCleaningPlan(plan.plan_id, "approve", "已复核")).rejects.toThrow("必须先生成预览");
    await mockApi.previewCleaningPlan(plan.plan_id);
    const approved = await mockApi.decideCleaningPlan(plan.plan_id, "approve", "已复核");
    expect(approved.status).toBe("approved");
    const job = await mockApi.executeCleaningPlan(plan.plan_id);
    expect(job.kind).toBe("cleaning_execute");
    expect(job.resource_id).toBe("dsv_04JABC");
  });

  it("confirms AnalysisSpec before starting a run and exposes evidence claims", async () => {
    const specs = await mockApi.listAnalysisSpecs();
    const confirmed = await mockApi.confirmAnalysisSpec(specs.items[0]!.spec_id);
    const job = await mockApi.createRun(confirmed.project_id, confirmed.spec_id, confirmed.dataset_version_id);
    expect(job.resource_type).toBe("analysis_run");
    const claims = await mockApi.listClaims();
    expect(claims.items[0]?.evidence_ids.length).toBeGreaterThan(0);
    expect(claims.items.every((claim) => claim.limitations.length > 0)).toBe(true);
  });
});
