import { afterEach, describe, expect, it, vi } from "vitest";
import type { Dataset, DatasetVersion, Page } from "./contracts";

async function loadRealClient() {
  vi.resetModules();
  vi.stubEnv("VITE_API_MODE", "real");
  vi.stubEnv("VITE_API_BASE_URL", "http://api.test/api/v1");
  vi.stubEnv("VITE_DEV_AUTH_TOKEN", "test-token");
  return import("./client");
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  vi.resetModules();
});

describe("apiClient real mode contract calls", () => {
  it("registers a persistent account through the public auth route", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json(
        { subject_id: "new-user", expires_in_seconds: 43_200 },
        { status: 201 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { apiClient } = await loadRealClient();
    await apiClient.register("new-user", "safe-password-2026");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/v1/auth/register",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ username: "new-user", password: "safe-password-2026" }),
        credentials: "include",
      }),
    );
  });

  it("activates a dataset version through the dataset-scoped route", async () => {
    const version: DatasetVersion = {
      version_id: "dsv_1",
      dataset_id: "ds_1",
      project_id: "prj_1",
      version_number: 2,
      status: "ready",
      kind: "cleaned",
      parent_version_id: "dsv_0",
      source_file_name: "customers.csv",
      sheet_name: null,
      file_hash: "sha256:abc",
      row_count: 10,
      column_count: 4,
      operation_summary: "cleaned",
      created_at: "2026-07-09T00:00:00Z",
    };
    const dataset: Dataset = {
      dataset_id: "ds_1",
      project_id: "prj_1",
      name: "customers",
      source_type: "csv",
      status: "active",
      current_version_id: "dsv_1",
      version_count: 2,
      created_at: "2026-07-09T00:00:00Z",
    };
    const page: Page<DatasetVersion> = {
      items: [version],
      page: 1,
      page_size: 20,
      total: 1,
      has_more: false,
    };
    const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) => {
      const value = String(url);
      if (value.endsWith("/activate")) return Response.json(dataset);
      if (value.endsWith("/versions?page=1&page_size=20")) return Response.json(page);
      return Response.json({ error: { message: "unexpected" } }, { status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const { apiClient } = await loadRealClient();
    const activated = await apiClient.activateDatasetVersion("prj_1", "ds_1", "dsv_1");

    expect(activated).toEqual(version);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://api.test/api/v1/projects/prj_1/datasets/ds_1/versions/dsv_1/activate",
      expect.objectContaining({
        method: "POST",
        headers: expect.any(Headers),
      }),
    );
    const headers = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer test-token");
    expect(headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("creates version comparisons with the contract field names", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
      Response.json({
        job_id: "job_1",
        kind: "version_comparison",
        status: "queued",
        progress: 0,
        current_step: null,
        resource_type: null,
        resource_id: null,
        retry_after_ms: null,
        created_at: "2026-07-09T00:00:00Z",
        updated_at: "2026-07-09T00:00:00Z",
        error: null,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { apiClient } = await loadRealClient();
    await apiClient.compareDatasetVersions("prj_1", "ds_1", "dsv_base", "dsv_compare");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/v1/projects/prj_1/datasets/ds_1/version-comparisons",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          base_version_id: "dsv_base",
          compare_version_id: "dsv_compare",
        }),
      }),
    );
    const headers = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("submits assistant turns to the conversation-scoped route", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) => Response.json({
      user_message: null,
      assistant_message: {
        message_id: "msg_1",
        conversation_id: "conv_1",
        role: "assistant",
        status: "queued",
        content: null,
        plan: null,
        answer: null,
        tool_calls: [],
        parent_message_id: null,
        job_id: "job_1",
        created_at: "2026-07-13T00:00:00Z",
        completed_at: null,
      },
      job: null,
    }, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);
    const { apiClient } = await loadRealClient();
    await apiClient.createAssistantMessage("prj_1", "conv_1", "检查数据质量");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/v1/projects/prj_1/assistant/conversations/conv_1/messages",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ content: "检查数据质量" }),
      }),
    );
    const headers = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Headers;
    expect(headers.get("Idempotency-Key")).toBeTruthy();
  });

  it("updates proposed assistant tool arguments through the project route", async () => {
    const fetchMock = vi.fn(async () => Response.json({
      tool_call_id: "tool_1",
      tool_name: "analysis.run",
      tool_version: "1.0.0",
      status: "proposed",
      requires_confirmation: true,
      arguments: { run_kind: "model" },
      result: null,
      result_resource_type: null,
      result_resource_id: null,
    }));
    vi.stubGlobal("fetch", fetchMock);
    const { apiClient } = await loadRealClient();
    await apiClient.updateAssistantToolCall("prj_1", "tool_1", { run_kind: "model" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api.test/api/v1/projects/prj_1/assistant/tool-calls/tool_1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ arguments: { run_kind: "model" } }),
      }),
    );
  });
});
