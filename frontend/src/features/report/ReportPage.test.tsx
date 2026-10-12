import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../../api/client";
import type { Artifact, Claim, Page } from "../../api/contracts";
import { seedArtifacts, seedClaims, seedProject, seedRuns } from "../../api/mockData";
import { ToastProvider } from "../../components/ui/ToastProvider";
import { AppProvider, useAppContext } from "../../context/AppContext";
import { ReportPage } from "./ReportPage";

vi.mock("../../hooks/useJobPolling", () => ({
  useJobPolling: () => ({ job: undefined, isTerminal: false }),
}));

const page = <T,>(items: T[]): Page<T> => ({
  items,
  page: 1,
  page_size: 100,
  total: items.length,
  has_more: false,
});

const run = seedRuns[0]!;
const claim: Claim = { ...seedClaims[0]!, run_id: run.run_id };

/** Verbatim evaluation payload from the 2026-10-11 acceptance run. */
const classificationMetrics = {
  accuracy: 0.333333,
  precision: 0.333333,
  recall: 0.333333,
  f1: 0.333333,
  confusion_matrix: { labels: ["no", "yes"], values: [[4, 8], [8, 4]] },
  log_loss: 0.732799,
  roc_auc: 0.263889,
  pr_auc: 0.398163,
  positive_class: "yes",
};

/** Regression runs report nested summaries and model comparisons instead. */
const regressionMetrics = {
  r2: 0.42,
  rmse: 1.8,
  residual_summary: { mean: -0.01, p95: 1.2 },
  comparison: [
    { model: "linear_regression", r2: 0.42 },
    { model: "random_forest", r2: 0.51 },
  ],
};

function artifact(overrides: Partial<Artifact> & Pick<Artifact, "artifact_id" | "type">): Artifact {
  return { ...seedArtifacts[0]!, run_id: run.run_id, ...overrides };
}

function metricsArtifacts(metrics: Record<string, unknown>): Artifact[] {
  return [
    artifact({
      artifact_id: "art_overview",
      type: "metric",
      result: { row_count: 240, column_count: 9, target_column: "churn", missing_ratio: 0 },
    }),
    artifact({
      artifact_id: "art_model",
      type: "model",
      result: { model_family: "logistic_regression", strategy: "stratified_kfold", target: "churn" },
    }),
    artifact({ artifact_id: "art_metrics", type: "metric", result: { metrics } }),
  ];
}

function Selection({ children }: { children: ReactNode }) {
  const { setProject } = useAppContext();
  useEffect(() => setProject(seedProject), [setProject]);
  return children;
}

function workspace() {
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}
    >
      <MemoryRouter>
        <ToastProvider>
          <AppProvider>
            <Selection>
              <ReportPage />
            </Selection>
          </AppProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Reads a rendered table as plain text rows.
 *
 * The metrics table nests other tables inside its cells, and jsdom's `querySelectorAll`
 * mixes the rows of a nested table with the outer one, so the assertions use the
 * table-scoped `tHead`/`tBodies`/`rows` collections instead.
 */
function tableShape(table: HTMLTableElement) {
  const head = table.tHead ? [...table.tHead.rows] : [];
  const body = [...table.tBodies].flatMap((section) => [...section.rows]);
  return {
    head: head.map((row) => [...row.cells].map((cell) => cell.textContent)),
    body: body.map((row) => [...row.cells].map((cell) => cell.textContent)),
  };
}

function mockArtifacts(items: Artifact[]) {
  vi.spyOn(apiClient, "listRuns").mockResolvedValue(page([run]));
  vi.spyOn(apiClient, "listClaims").mockResolvedValue(page([claim]));
  vi.spyOn(apiClient, "listArtifacts").mockResolvedValue(page(items));
}

beforeEach(() => {
  vi.spyOn(apiClient, "getCapabilities").mockResolvedValue({
    api_version: "v1",
    supported_file_types: ["csv"],
    max_upload_bytes: 100,
    natural_language_analysis: false,
    llm: { assistant: false, evidence_narrative: false },
    auth_enabled: true,
    polling: { initial_interval_ms: 1000, steady_interval_ms: 3000, background_interval_ms: 10000 },
  });
});

afterEach(() => vi.restoreAllMocks());

describe("ReportPage context metrics", () => {
  it("renders a confusion matrix as a table instead of stringifying it", async () => {
    mockArtifacts(metricsArtifacts(classificationMetrics));
    const { container } = workspace();
    await screen.findByRole("heading", { name: "4. 模型指标" });

    expect(container.textContent).not.toContain("[object Object]");
    expect(screen.getByText("240")).toBeInTheDocument();
    expect(screen.getByText("ROC-AUC")).toBeInTheDocument();
    expect(screen.getByText("0.263889")).toBeInTheDocument();
    expect(screen.getAllByText("0.333333")).toHaveLength(4);

    const row = screen.getByText("CONFUSION-MATRIX").closest("tr");
    expect(row).not.toBeNull();
    const matrixTable = row!.querySelector("table");
    expect(matrixTable).not.toBeNull();
    expect(tableShape(matrixTable as HTMLTableElement)).toEqual({
      head: [["实际 \\ 预测", "no", "yes"]],
      body: [["no", "4", "8"], ["yes", "8", "4"]],
    });
  });

  it("renders regression summaries and model comparisons without losing values", async () => {
    mockArtifacts(metricsArtifacts(regressionMetrics));
    const { container } = workspace();
    await screen.findByRole("heading", { name: "4. 模型指标" });

    expect(container.textContent).not.toContain("[object Object]");
    expect(screen.getByText("RESIDUAL-SUMMARY")).toBeInTheDocument();
    expect(screen.getByText("mean")).toBeInTheDocument();
    expect(screen.getByText("-0.01")).toBeInTheDocument();

    const comparisonTable = screen.getByText("COMPARISON").closest("tr")!.querySelector("table");
    expect(tableShape(comparisonTable as HTMLTableElement)).toEqual({
      head: [["model", "r2"]],
      body: [["linear regression", "0.42"], ["random forest", "0.51"]],
    });
  });
});
