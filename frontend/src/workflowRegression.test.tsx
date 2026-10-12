import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./api/client";
import type { AnalysisSpec, DatasetSchema, Job, Page } from "./api/contracts";
import { seedAnalysisSpec, seedCleaningPlan, seedColumns, seedDataset, seedProject, seedVersions } from "./api/mockData";
import { AppShell } from "./components/shell/AppShell";
import { ToastProvider } from "./components/ui/ToastProvider";
import { AppProvider, useAppContext } from "./context/AppContext";
import { CleaningPage } from "./features/cleaning/CleaningPage";
import { ExplorePage } from "./features/explore/ExplorePage";
vi.mock("./hooks/useJobPolling", () => ({ useJobPolling: () => ({ job: undefined, isTerminal: false }) }));
const page = <T,>(items: T[]): Page<T> => ({ items, page: 1, page_size: 100, total: items.length, has_more: false });
const job = { job_id: "qa-job" } as Job;
const schema: DatasetSchema = { dataset_version_id: seedVersions[0]!.version_id, revision: 1, low_confidence_count: 0, columns: seedColumns };
function Selection({ children }: { children: ReactNode }) {
  const { setProject, setDataset, setVersion } = useAppContext();
  useEffect(() => { setProject(seedProject); setDataset(seedDataset); setVersion(seedVersions[0]!); }, [setProject, setDataset, setVersion]);
  return children;
}
function workspace(children: ReactNode, initialize = true) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MemoryRouter><ToastProvider><AppProvider>{initialize ? <Selection>{children}</Selection> : children}</AppProvider></ToastProvider></MemoryRouter>
  </QueryClientProvider>);
}
beforeEach(() => {
  vi.spyOn(apiClient, "getDatasetSchema").mockResolvedValue(schema);
  vi.spyOn(apiClient, "listDatasetVersions").mockResolvedValue(page(seedVersions));
  vi.spyOn(apiClient, "listCleaningPlans").mockResolvedValue(page([]));
  vi.spyOn(apiClient, "listAnalysisSpecs").mockResolvedValue(page([structuredClone(seedAnalysisSpec)]));
  vi.spyOn(apiClient, "listRuns").mockResolvedValue(page([]));
  vi.spyOn(apiClient, "listProjects").mockResolvedValue(page([seedProject]));
  vi.spyOn(apiClient, "listDatasets").mockResolvedValue(page([seedDataset]));
  vi.spyOn(apiClient, "getCapabilities").mockResolvedValue({ api_version: "v1", supported_file_types: ["csv"], max_upload_bytes: 100, natural_language_analysis: false, llm: { assistant: false, evidence_narrative: false }, auth_enabled: true, polling: { initial_interval_ms: 1000, steady_interval_ms: 3000, background_interval_ms: 10000 } });
});
afterEach(() => vi.restoreAllMocks());
describe("first cleaning plan", () => {
  it.each(["保存草稿", "生成预览"])("allows %s with no existing plan", async (action) => {
    const create = vi.spyOn(apiClient, "createCleaningPlan").mockImplementation(async (pid, vid, operations) => ({ ...seedCleaningPlan, project_id: pid, source_version_id: vid, operations, status: "draft", preview_artifact_id: null }));
    const preview = vi.spyOn(apiClient, "previewCleaningPlan").mockResolvedValue(job);
    workspace(<CleaningPage />);
    const button = await screen.findByRole("button", { name: action });
    expect(button).toBeDisabled();
    await waitFor(() => expect(screen.getByRole("button", { name: "缺失值填充" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "缺失值填充" })); expect(button).toBeEnabled(); fireEvent.click(button);
    await waitFor(() => expect(create).toHaveBeenCalledWith(seedProject.project_id, seedVersions[0]!.version_id, expect.arrayContaining([expect.objectContaining({ operation: "impute_missing" })])));
    if (action === "生成预览") await waitFor(() => expect(preview).toHaveBeenCalledWith(seedProject.project_id, seedCleaningPlan.plan_id));
    else expect(await screen.findByText("清洗计划草稿已保存")).toBeInTheDocument();
  });
  it("saves edited operations before previewing an existing draft", async () => {
    const plan = { ...seedCleaningPlan, status: "draft" as const, preview_artifact_id: null };
    vi.mocked(apiClient.listCleaningPlans).mockResolvedValue(page([plan]));
    const update = vi.spyOn(apiClient, "updateCleaningPlan").mockImplementation(async (_pid, _plan, _name, operations) => ({ ...plan, operations, revision: plan.revision + 1 }));
    const preview = vi.spyOn(apiClient, "previewCleaningPlan").mockResolvedValue(job);
    workspace(<CleaningPage />); await screen.findByRole("heading", { name: "清洗计划" });
    await waitFor(() => expect(screen.getByRole("button", { name: "缺失标记" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "缺失标记" })); fireEvent.click(screen.getByRole("button", { name: "生成预览" }));
    await waitFor(() => expect(preview).toHaveBeenCalled());
    expect(update.mock.calls[0]![3]).toEqual(expect.arrayContaining([expect.objectContaining({ operation: "add_missing_indicator" })]));
    expect(update.mock.invocationCallOrder[0]!).toBeLessThan(preview.mock.invocationCallOrder[0]!);
  });
  it("keeps executed plans locked", async () => {
    vi.mocked(apiClient.listCleaningPlans).mockResolvedValue(page([{ ...seedCleaningPlan, status: "executed" }]));
    workspace(<CleaningPage />); expect(await screen.findByRole("button", { name: "保存草稿" })).toBeDisabled(); expect(screen.getByRole("button", { name: "生成预览" })).toBeDisabled();
  });
});
describe("run current analysis parameters", () => {
  function edit() { fireEvent.click(screen.getByLabelText("monthly_fee")); fireEvent.change(screen.getByLabelText("随机种子"), { target: { value: "99" } }); fireEvent.click(screen.getByRole("button", { name: "确认并运行" })); }
  it("updates a saved draft before confirmation and binds the updated spec", async () => {
    const next = { ...seedAnalysisSpec, revision: 3, included_columns: ["plan_type", "income"], random_seed: 99 };
    const update = vi.spyOn(apiClient, "updateAnalysisSpec").mockResolvedValue(next);
    const confirm = vi.spyOn(apiClient, "confirmAnalysisSpec").mockResolvedValue({ ...next, status: "confirmed" });
    const run = vi.spyOn(apiClient, "createRun").mockResolvedValue(job);
    workspace(<ExplorePage />); await screen.findByRole("heading", { name: "分析设计" }); edit();
    await waitFor(() => expect(run).toHaveBeenCalledWith(seedProject.project_id, next.spec_id, next.dataset_version_id));
    expect(update).toHaveBeenCalledWith(seedProject.project_id, seedAnalysisSpec, expect.objectContaining({ included_columns: ["plan_type", "income"], random_seed: 99 }));
    expect(update.mock.invocationCallOrder[0]!).toBeLessThan(confirm.mock.invocationCallOrder[0]!); expect(confirm.mock.invocationCallOrder[0]!).toBeLessThan(run.mock.invocationCallOrder[0]!);
  });
  it("creates a new spec when a confirmed spec is edited, preserving history", async () => {
    vi.mocked(apiClient.listAnalysisSpecs).mockResolvedValue(page([{ ...seedAnalysisSpec, status: "confirmed" }]));
    const next: AnalysisSpec = { ...seedAnalysisSpec, spec_id: "new-spec", revision: 1, random_seed: 99 };
    const create = vi.spyOn(apiClient, "createAnalysisSpec").mockResolvedValue(next); const update = vi.spyOn(apiClient, "updateAnalysisSpec");
    vi.spyOn(apiClient, "confirmAnalysisSpec").mockResolvedValue({ ...next, status: "confirmed" }); const run = vi.spyOn(apiClient, "createRun").mockResolvedValue(job);
    workspace(<ExplorePage />); await screen.findByRole("heading", { name: "分析设计" }); edit();
    await waitFor(() => expect(run).toHaveBeenCalledWith(seedProject.project_id, "new-spec", next.dataset_version_id));
    expect(create).toHaveBeenCalledWith(seedProject.project_id, expect.objectContaining({ random_seed: 99, included_columns: ["plan_type", "income"] })); expect(create.mock.calls[0]![1]).not.toHaveProperty("spec_id"); expect(update).not.toHaveBeenCalled();
  });
  it("reuses an unchanged confirmed spec", async () => {
    vi.mocked(apiClient.listAnalysisSpecs).mockResolvedValue(page([{ ...seedAnalysisSpec, status: "confirmed" }]));
    const create = vi.spyOn(apiClient, "createAnalysisSpec"); const confirm = vi.spyOn(apiClient, "confirmAnalysisSpec"); const run = vi.spyOn(apiClient, "createRun").mockResolvedValue(job);
    workspace(<ExplorePage />); fireEvent.click(await screen.findByRole("button", { name: "确认并运行" }));
    await waitFor(() => expect(run).toHaveBeenCalledWith(seedProject.project_id, seedAnalysisSpec.spec_id, seedAnalysisSpec.dataset_version_id)); expect(create).not.toHaveBeenCalled(); expect(confirm).not.toHaveBeenCalled();
  });
  it("does not start a run when saving changed parameters fails", async () => {
    vi.spyOn(apiClient, "updateAnalysisSpec").mockRejectedValue(new Error("revision conflict")); const confirm = vi.spyOn(apiClient, "confirmAnalysisSpec"); const run = vi.spyOn(apiClient, "createRun");
    workspace(<ExplorePage />); await screen.findByRole("heading", { name: "分析设计" }); edit();
    await screen.findByText("revision conflict"); await waitFor(() => expect(screen.getByRole("button", { name: "确认并运行" })).toBeEnabled()); expect(confirm).not.toHaveBeenCalled(); expect(run).not.toHaveBeenCalled();
  });
});
describe("persisted active dataset version", () => {
  it("selects the active dataset and rolled-back version on fresh mounts", async () => {
    const raw = seedVersions[2]!; vi.mocked(apiClient.listProjects).mockResolvedValue(page([{ ...seedProject, current_dataset_version_id: raw.version_id }]));
    vi.mocked(apiClient.listDatasets).mockResolvedValue(page([{ ...seedDataset, dataset_id: "newer-dataset", current_version_id: "newer-version" }, { ...seedDataset, current_version_id: raw.version_id }]));
    for (let i = 0; i < 2; i++) {
      const view = workspace(<AppShell><span>workspace</span></AppShell>, false);
      await waitFor(() => expect(screen.getByRole("combobox", { name: "当前数据版本" })).toHaveValue(raw.version_id)); expect(apiClient.listDatasetVersions).toHaveBeenLastCalledWith(seedProject.project_id, seedDataset.dataset_id);
      fireEvent.change(screen.getByRole("combobox", { name: "当前数据版本" }), { target: { value: seedVersions[0]!.version_id } }); expect(screen.getByRole("combobox", { name: "当前数据版本" })).toHaveValue(seedVersions[0]!.version_id); view.unmount();
    }
  });
  it("falls back to the newest version when no active version is available", async () => {
    vi.mocked(apiClient.listDatasets).mockResolvedValue(page([{ ...seedDataset, current_version_id: null }])); workspace(<AppShell><span>workspace</span></AppShell>, false);
    await waitFor(() => expect(screen.getByRole("combobox", { name: "当前数据版本" })).toHaveValue(seedVersions[0]!.version_id));
  });
});
