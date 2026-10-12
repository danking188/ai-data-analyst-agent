import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../../api/client";
import type {
  AssistantConversation,
  AssistantMessage,
  AssistantMetrics,
  AssistantTraceReplay,
  Page,
} from "../../api/contracts";
import { seedProject } from "../../api/mockData";
import { ToastProvider } from "../../components/ui/ToastProvider";
import { AppProvider, useAppContext } from "../../context/AppContext";
import { AssistantPage } from "./AssistantPage";

const page = <T,>(items: T[]): Page<T> => ({
  items,
  page: 1,
  page_size: 100,
  total: items.length,
  has_more: false,
});

const metrics: AssistantMetrics = {
  window_days: 7,
  turn_count: 4,
  succeeded_count: 3,
  failed_count: 1,
  input_tokens: 1200,
  output_tokens: 400,
  average_latency_ms: 900,
  p95_latency_ms: 2000,
  tool_call_count: 2,
  tool_succeeded_count: 2,
  tool_failed_count: 0,
  tool_rejected_count: 0,
};

function conversation(
  conversation_id: string,
  title: string,
  status: AssistantConversation["status"],
): AssistantConversation {
  return {
    conversation_id,
    project_id: seedProject.project_id,
    title,
    status,
    dataset_version_id: null,
    created_by: "dev-user",
    created_at: "2026-10-11T08:00:00Z",
    updated_at: "2026-10-11T09:00:00Z",
    archived_at: status === "archived" ? "2026-10-11T09:30:00Z" : null,
  };
}

const activeConversation = conversation("conv_active", "进行中的会话", "active");
const archivedConversation = conversation("conv_archived", "已归档的会话", "archived");

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
              <AssistantPage />
            </Selection>
          </AppProvider>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockConversations(items: AssistantConversation[]) {
  vi.spyOn(apiClient, "listAssistantConversations").mockResolvedValue(page(items));
}

beforeEach(() => {
  vi.spyOn(apiClient, "getCapabilities").mockResolvedValue({
    api_version: "v1",
    supported_file_types: ["csv"],
    max_upload_bytes: 100,
    natural_language_analysis: false,
    llm: { assistant: true, evidence_narrative: false },
    auth_enabled: true,
    polling: { initial_interval_ms: 1000, steady_interval_ms: 3000, background_interval_ms: 10000 },
  });
  vi.spyOn(apiClient, "getAssistantMetrics").mockResolvedValue(metrics);
  vi.spyOn(apiClient, "listAssistantMessages").mockResolvedValue(page([]));
});

afterEach(() => vi.restoreAllMocks());

const completedMessage: AssistantMessage = {
  message_id: "msg_completed",
  conversation_id: activeConversation.conversation_id,
  role: "assistant",
  status: "completed",
  content: "已基于记录的证据作答。",
  plan: null,
  answer: { summary: "准确率为 0.8。", findings: [], next_actions: [], limitations: [] },
  tool_calls: [],
  parent_message_id: null,
  job_id: null,
  created_at: "2026-10-11T09:00:00Z",
  completed_at: "2026-10-11T09:01:00Z",
};

const traceReplay: AssistantTraceReplay = {
  trace: {
    llm_run_id: "llmrun_1",
    message_id: completedMessage.message_id,
    project_id: seedProject.project_id,
    job_id: null,
    provider: "fake",
    model: "fake-model",
    prompt_name: "assistant.answer",
    prompt_version: "1.0.0",
    status: "succeeded",
    model_call_count: 2,
    tool_call_count: 1,
    input_tokens: 800,
    output_tokens: 200,
    latency_ms: 1500,
    context_manifest: { prompt_version: "1.0.0" },
    error: null,
    tool_calls: [],
    created_at: "2026-10-11T09:00:00Z",
    completed_at: "2026-10-11T09:01:00Z",
  },
  verified: true,
  replayed_state: "complete",
  checks: [
    { name: "state_transitions", passed: true, details: {} },
    { name: "run_terminal_state", passed: true, details: {} },
    { name: "tool_call_count", passed: true, details: {} },
    { name: "tool_terminal_states", passed: true, details: {} },
  ],
};

describe("AssistantPage conversations", () => {
  it("selects the active conversation and labels the archived one", async () => {
    mockConversations([archivedConversation, activeConversation]);
    workspace();

    expect(await screen.findByRole("heading", { name: "进行中的会话" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "已归档会话" })).toBeInTheDocument();
    expect(screen.getByText("已归档")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "归档会话" })).toBeInTheDocument();
    expect(screen.getByText("1 进行中 · 1 已归档")).toBeInTheDocument();
  });

  it("restores an archived conversation instead of archiving it again", async () => {
    const update = vi
      .spyOn(apiClient, "updateAssistantConversation")
      .mockResolvedValue({ ...archivedConversation, status: "active", archived_at: null });
    mockConversations([archivedConversation, activeConversation]);
    workspace();

    fireEvent.click(await screen.findByText(archivedConversation.title));
    fireEvent.click(await screen.findByRole("button", { name: "恢复会话" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(seedProject.project_id, archivedConversation.conversation_id, {
        status: "active",
      }),
    );
    expect(await screen.findByText("会话已恢复")).toBeInTheDocument();
  });

  it("archives the selected conversation and releases the selection", async () => {
    const update = vi
      .spyOn(apiClient, "updateAssistantConversation")
      .mockResolvedValue({ ...activeConversation, status: "archived", archived_at: "2026-10-11T10:00:00Z" });
    mockConversations([activeConversation]);
    workspace();

    fireEvent.click(await screen.findByRole("button", { name: "归档会话" }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(seedProject.project_id, activeConversation.conversation_id, {
        status: "archived",
      }),
    );
    expect(await screen.findByText("会话已归档")).toBeInTheDocument();
  });

  it("does not auto-select when every conversation is archived", async () => {
    mockConversations([archivedConversation]);
    workspace();

    expect(await screen.findByText("已归档")).toBeInTheDocument();
    // A selection would render the archived conversation's header actions.
    expect(screen.queryByRole("button", { name: "归档会话" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "恢复会话" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(archivedConversation.title));
    expect(await screen.findByRole("button", { name: "恢复会话" })).toBeInTheDocument();
  });

  it("reports a failed status change instead of failing silently", async () => {
    vi.spyOn(apiClient, "updateAssistantConversation").mockRejectedValue(new Error("会话状态冲突"));
    mockConversations([activeConversation]);
    workspace();

    fireEvent.click(await screen.findByRole("button", { name: "归档会话" }));

    expect(await screen.findByText("会话状态冲突")).toBeInTheDocument();
  });
});

describe("AssistantPage trace compare", () => {
  it("explains an invalid candidate that was corrected and still failed", async () => {
    mockConversations([activeConversation]);
    vi.mocked(apiClient.listAssistantMessages).mockResolvedValue(page([completedMessage]));
    vi.spyOn(apiClient, "replayAssistantTrace").mockResolvedValue(traceReplay);
    vi.spyOn(apiClient, "compareAssistantTrace").mockResolvedValue({
      source_message_id: completedMessage.message_id,
      source_run_id: "llmrun_1",
      replay_mode: "counterfactual_no_tools",
      candidates: [
        {
          label: "current",
          model: "fake-model",
          prompt_variant: "current",
          answer: { summary: "评估集共有 3 个标签。", findings: [], next_actions: [], limitations: [] },
          citation_valid: false,
          validation_error: "初稿：finding 1 contains unsupported numbers: 3；纠正后仍不合格：summary contains numbers not established by a cited finding: 3",
          correction_attempted: true,
          similarity_to_original: 0.5,
          input_tokens: 300,
          output_tokens: 30,
          latency_ms: 3000,
        },
      ],
    });
    workspace();

    fireEvent.click(await screen.findByRole("button", { name: "回放校验" }));
    fireEvent.click(await screen.findByRole("button", { name: "对比当前 Prompt 与证据审计 Prompt" }));

    expect(await screen.findByText(/引用失败（已重试并纠正）/)).toBeInTheDocument();
    expect(await screen.findByText(/纠正后仍不合格/)).toBeInTheDocument();
  });
});
