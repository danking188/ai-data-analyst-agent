import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Bot,
  Check,
  ChevronRight,
  CircleStop,
  FileSearch,
  ExternalLink,
  Link2,
  MessageSquarePlus,
  RefreshCw,
  Pencil,
  Send,
  ThumbsDown,
  ThumbsUp,
  Wrench,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "../../api/client";
import type { AssistantMessage, AssistantToolCall } from "../../api/contracts";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { LoadingBlock } from "../../components/ui/LoadingBlock";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useToast } from "../../components/ui/ToastProvider";
import { useAppContext } from "../../context/AppContext";
import { queryKeys } from "../../lib/queryKeys";

export function AssistantPage() {
  const { project, version } = useAppContext();
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [selectedCitation, setSelectedCitation] = useState<string | null>(null);
  const [feedbackSent, setFeedbackSent] = useState<Set<string>>(new Set());
  const messageEndRef = useRef<HTMLDivElement>(null);

  const capabilitiesQuery = useQuery({
    queryKey: ["system", "capabilities"],
    queryFn: () => apiClient.getCapabilities(),
  });
  const enabled = capabilitiesQuery.data?.llm.assistant ?? false;
  const conversationsQuery = useQuery({
    queryKey: queryKeys.assistantConversations(project?.project_id ?? "none"),
    queryFn: () => apiClient.listAssistantConversations(project!.project_id),
    enabled: Boolean(project && enabled),
  });
  const metricsQuery = useQuery({
    queryKey: ["assistant", project?.project_id ?? "none", "metrics", 7],
    queryFn: () => apiClient.getAssistantMetrics(project!.project_id),
    enabled: Boolean(project && enabled),
  });

  useEffect(() => {
    if (!selectedConversationId && conversationsQuery.data?.items[0]) {
      setSelectedConversationId(conversationsQuery.data.items[0].conversation_id);
    }
  }, [conversationsQuery.data, selectedConversationId]);

  const messagesQuery = useQuery({
    queryKey: queryKeys.assistantMessages(
      project?.project_id ?? "none",
      selectedConversationId ?? "none",
    ),
    queryFn: () => apiClient.listAssistantMessages(project!.project_id, selectedConversationId!),
    enabled: Boolean(project && selectedConversationId && enabled),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) => ["queued", "processing"].includes(item.status))
        ? 1500
        : false,
  });

  useEffect(() => {
    const end = messageEndRef.current;
    if (end && typeof end.scrollIntoView === "function") {
      end.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messagesQuery.data?.items.length]);

  const selectedConversation = conversationsQuery.data?.items.find(
    (item) => item.conversation_id === selectedConversationId,
  );
  const messages = messagesQuery.data?.items ?? [];
  const toolCalls = useMemo(
    () => messages.flatMap((message) => message.tool_calls.map((call) => ({ call, message }))),
    [messages],
  );

  const createConversation = useMutation({
    mutationFn: () =>
      apiClient.createAssistantConversation(project!.project_id, {
        title: "新分析会话",
        dataset_version_id: version?.version_id ?? null,
      }),
    onSuccess: async (conversation) => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assistantConversations(project!.project_id),
      });
      setSelectedConversationId(conversation.conversation_id);
    },
    onError: (error) => pushToast(error instanceof Error ? error.message : "会话创建失败", "error"),
  });

  const sendMessage = useMutation({
    mutationFn: (content: string) =>
      apiClient.createAssistantMessage(project!.project_id, selectedConversationId!, content),
    onSuccess: async () => {
      setDraft("");
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.assistantMessages(project!.project_id, selectedConversationId!),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.assistantConversations(project!.project_id),
        }),
      ]);
    },
    onError: (error) => pushToast(error instanceof Error ? error.message : "问题提交失败", "error"),
  });

  const planDecision = useMutation({
    mutationFn: ({ message, decision }: { message: AssistantMessage; decision: "approve" | "reject" }) =>
      apiClient.confirmAssistantPlan(
        project!.project_id,
        message.message_id,
        decision,
        message.tool_calls.filter((item) => item.status === "proposed").map((item) => item.tool_call_id),
      ),
    onSuccess: async (_, variables) => {
      pushToast(variables.decision === "approve" ? "计划已确认" : "计划已取消");
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assistantMessages(project!.project_id, selectedConversationId!),
      });
    },
    onError: (error) => pushToast(error instanceof Error ? error.message : "计划处理失败", "error"),
  });

  const updateToolCall = useMutation({
    mutationFn: ({ call, argumentsValue }: {
      call: AssistantToolCall;
      argumentsValue: Record<string, unknown>;
    }) => apiClient.updateAssistantToolCall(
      project!.project_id,
      call.tool_call_id,
      argumentsValue,
    ),
    onSuccess: async () => {
      pushToast("工具参数已重新校验并保存");
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assistantMessages(project!.project_id, selectedConversationId!),
      });
    },
    onError: (error) => pushToast(error instanceof Error ? error.message : "参数保存失败", "error"),
  });

  const cancelMessage = useMutation({
    mutationFn: (messageId: string) => apiClient.cancelAssistantMessage(project!.project_id, messageId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.assistantMessages(project!.project_id, selectedConversationId!),
      }),
  });
  const retryMessage = useMutation({
    mutationFn: (messageId: string) => apiClient.retryAssistantMessage(project!.project_id, messageId),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.assistantMessages(project!.project_id, selectedConversationId!),
      }),
  });
  const feedback = useMutation({
    mutationFn: ({ messageId, rating }: { messageId: string; rating: "helpful" | "not_helpful" }) =>
      apiClient.createAssistantFeedback(project!.project_id, messageId, rating),
    onSuccess: (_, variables) => {
      setFeedbackSent((current) => new Set(current).add(variables.messageId));
      pushToast("反馈已记录");
    },
  });
  const archiveConversation = useMutation({
    mutationFn: () =>
      apiClient.updateAssistantConversation(project!.project_id, selectedConversationId!, {
        status: "archived",
      }),
    onSuccess: async () => {
      setSelectedConversationId(null);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.assistantConversations(project!.project_id),
      });
    },
  });

  if (capabilitiesQuery.isLoading) return <LoadingBlock rows={4} />;

  return (
    <>
      <header className="page-heading compact assistant-heading">
        <div>
          <h1>AI 分析助手</h1>
          <p>{version ? `数据版本 v${version.version_number} · ${version.row_count.toLocaleString()} 行` : "未选择数据版本"}</p>
        </div>
        <Button
          disabled={!project || !enabled || createConversation.isPending}
          icon={<MessageSquarePlus size={16} />}
          onClick={() => createConversation.mutate()}
          variant="primary"
        >
          新建会话
        </Button>
      </header>

      {!enabled ? (
        <div className="assistant-unavailable">
          <Bot size={30} />
          <h2>Assistant 尚未启用</h2>
          <p>请配置 LLM API 后重新部署。</p>
        </div>
      ) : !project ? (
        <EmptyState title="尚未选择项目" description="选择项目后可以创建分析会话。" />
      ) : (
        <section className="assistant-workspace">
          <aside className="assistant-conversations" aria-label="分析会话">
            <header>
              <h2>会话</h2>
              <span>{conversationsQuery.data?.total ?? 0}</span>
            </header>
            {conversationsQuery.isLoading ? <LoadingBlock rows={3} /> : null}
            <div className="assistant-conversation-list">
              {conversationsQuery.data?.items.map((conversation) => (
                <button
                  className={conversation.conversation_id === selectedConversationId ? "is-active" : ""}
                  key={conversation.conversation_id}
                  onClick={() => setSelectedConversationId(conversation.conversation_id)}
                >
                  <strong>{conversation.title}</strong>
                  <span>
                    {conversation.dataset_version_id ? "已绑定数据" : "无数据版本"}
                    <ChevronRight size={14} />
                  </span>
                </button>
              ))}
            </div>
          </aside>

          <div className="assistant-thread">
            {selectedConversation ? (
              <header className="assistant-thread__header">
                <div>
                  <h2>{selectedConversation.title}</h2>
                  <span>{selectedConversation.dataset_version_id ?? "未绑定数据版本"}</span>
                </div>
                <button
                  aria-label="归档会话"
                  className="icon-button"
                  disabled={archiveConversation.isPending}
                  onClick={() => archiveConversation.mutate()}
                  title="归档会话"
                >
                  <Archive size={17} />
                </button>
              </header>
            ) : null}

            <div className="assistant-messages" aria-live="polite">
              {messagesQuery.isLoading ? <LoadingBlock rows={4} /> : null}
              {!messagesQuery.isLoading && selectedConversation && messages.length === 0 ? (
                <EmptyState title="开始分析" description="输入一个与当前项目数据有关的问题。" />
              ) : null}
              {!selectedConversation ? (
                <EmptyState title="选择一个会话" description="从左侧打开会话，或新建分析会话。" />
              ) : null}
              {messages.map((message) => (
                <MessageItem
                  feedbackSent={feedbackSent.has(message.message_id)}
                  key={message.message_id}
                  message={message}
                  onCancel={() => cancelMessage.mutate(message.message_id)}
                  onCitation={setSelectedCitation}
                  onDecision={(decision) => planDecision.mutate({ message, decision })}
                  onFeedback={(rating) => feedback.mutate({ messageId: message.message_id, rating })}
                  onRetry={() => retryMessage.mutate(message.message_id)}
                  onUpdateToolCall={(call, argumentsValue) => updateToolCall.mutateAsync({ call, argumentsValue }).then(() => undefined)}
                />
              ))}
              <div ref={messageEndRef} />
            </div>

            <form
              className="assistant-composer"
              onSubmit={(event) => {
                event.preventDefault();
                const content = draft.trim();
                if (content && selectedConversationId) sendMessage.mutate(content);
              }}
            >
              <textarea
                aria-label="分析问题"
                disabled={!selectedConversation || selectedConversation.status !== "active" || sendMessage.isPending}
                maxLength={12000}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder="询问数据质量、分析结果或建模方案"
                rows={3}
                value={draft}
              />
              <button
                aria-label="发送问题"
                className="assistant-send"
                disabled={!draft.trim() || !selectedConversation || sendMessage.isPending}
                type="submit"
              >
                <Send size={18} />
              </button>
            </form>
          </div>

          <aside className="assistant-activity" aria-label="工具活动">
            <header>
              <Wrench size={17} />
              <h2>工具活动</h2>
            </header>
            {metricsQuery.data ? (
              <dl className="assistant-metrics" aria-label="近 7 天运行指标">
                <div>
                  <dt>成功率</dt>
                  <dd>
                    {metricsQuery.data.turn_count
                      ? `${Math.round((metricsQuery.data.succeeded_count / metricsQuery.data.turn_count) * 100)}%`
                      : "-"}
                  </dd>
                </div>
                <div>
                  <dt>Token</dt>
                  <dd>{(metricsQuery.data.input_tokens + metricsQuery.data.output_tokens).toLocaleString()}</dd>
                </div>
                <div>
                  <dt>P95</dt>
                  <dd>{metricsQuery.data.p95_latency_ms ? `${(metricsQuery.data.p95_latency_ms / 1000).toFixed(1)}s` : "-"}</dd>
                </div>
              </dl>
            ) : null}
            {toolCalls.length ? (
              <ol>
                {toolCalls.map(({ call }) => (
                  <li key={call.tool_call_id}>
                    <span><StatusBadge status={call.status} /></span>
                    <strong>{call.tool_name}</strong>
                    <small>{call.tool_version}</small>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="assistant-activity__empty">暂无工具调用</p>
            )}
          </aside>
        </section>
      )}

      {selectedCitation && project ? (
        <CitationDrawer
          citationId={selectedCitation}
          onClose={() => setSelectedCitation(null)}
          projectId={project.project_id}
        />
      ) : null}
    </>
  );
}

function MessageItem({
  message,
  feedbackSent,
  onCancel,
  onRetry,
  onDecision,
  onCitation,
  onFeedback,
  onUpdateToolCall,
}: {
  message: AssistantMessage;
  feedbackSent: boolean;
  onCancel: () => void;
  onRetry: () => void;
  onDecision: (decision: "approve" | "reject") => void;
  onCitation: (citationId: string) => void;
  onFeedback: (rating: "helpful" | "not_helpful") => void;
  onUpdateToolCall: (
    call: AssistantToolCall,
    argumentsValue: Record<string, unknown>,
  ) => Promise<void>;
}) {
  const isAssistant = message.role === "assistant";
  return (
    <article className={`assistant-message assistant-message--${isAssistant ? "assistant" : "user"}`}>
      <header>
        <span>{isAssistant ? <Bot size={16} /> : "你"}</span>
        <StatusBadge status={message.status} />
      </header>
      {message.content ? <p className="assistant-message__summary">{message.content}</p> : null}
      {message.answer?.findings.map((finding, index) => (
        <div className="assistant-finding" key={`${message.message_id}-${index}`}>
          <span>L{finding.claim_level}</span>
          <p>{finding.text}</p>
          <div>
            {finding.citation_ids.map((citationId) => (
              <button key={citationId} onClick={() => onCitation(citationId)}>
                <Link2 size={13} />
                {citationId}
              </button>
            ))}
          </div>
        </div>
      ))}
      {message.answer?.limitations.length ? (
        <ul className="assistant-limitations">
          {message.answer.limitations.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : null}
      {message.plan ? (
        <div className="assistant-plan">
          <header>
            <h3>{message.plan.objective}</h3>
            <span>{message.plan.estimated_tool_calls} 个工具调用</span>
          </header>
          <ol>
            {message.plan.steps.map((step) => (
              <li key={step.position}>
                <span>{step.position}</span>
                <div><strong>{step.title}</strong><p>{step.purpose}</p><code>{step.tool_name}</code></div>
              </li>
            ))}
          </ol>
          {message.tool_calls.some((call) => call.requires_confirmation) ? (
            <div className="assistant-proposals">
              {message.tool_calls.filter((call) => call.requires_confirmation).map((call) => (
                <ToolProposal
                  call={call}
                  key={call.tool_call_id}
                  onUpdate={(argumentsValue) => onUpdateToolCall(call, argumentsValue)}
                />
              ))}
            </div>
          ) : null}
          {message.status === "awaiting_confirmation" ? (
            <footer>
              <Button icon={<X size={15} />} onClick={() => onDecision("reject")} size="sm">取消计划</Button>
              <Button icon={<Check size={15} />} onClick={() => onDecision("approve")} size="sm" variant="primary">确认执行</Button>
            </footer>
          ) : null}
        </div>
      ) : null}
      {isAssistant ? (
        <footer className="assistant-message__actions">
          {["queued", "processing"].includes(message.status) ? (
            <button onClick={onCancel}><CircleStop size={14} />取消</button>
          ) : null}
          {["failed", "cancelled"].includes(message.status) ? (
            <button onClick={onRetry}><RefreshCw size={14} />重试</button>
          ) : null}
          {message.status === "completed" && !feedbackSent ? (
            <>
              <button aria-label="回答有帮助" onClick={() => onFeedback("helpful")}><ThumbsUp size={14} /></button>
              <button aria-label="回答没有帮助" onClick={() => onFeedback("not_helpful")}><ThumbsDown size={14} /></button>
            </>
          ) : null}
        </footer>
      ) : null}
    </article>
  );
}

function ToolProposal({
  call,
  onUpdate,
}: {
  call: AssistantToolCall;
  onUpdate: (argumentsValue: Record<string, unknown>) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [jsonValue, setJsonValue] = useState(() => JSON.stringify(call.arguments, null, 2));
  const [error, setError] = useState<string | null>(null);
  const details = proposalDetails(call);
  const cleaningOperations = call.tool_name === "cleaning.draft_plan" && Array.isArray(call.arguments.operations)
    ? call.arguments.operations
    : [];
  const resourceHref = call.result_resource_type === "cleaning_plan"
    ? "/quality/cleaning"
    : call.result_resource_type === "analysis_run"
      ? "/model"
      : call.result_resource_type
        ? "/explore"
        : null;
  return (
    <section className="assistant-proposal">
      <header>
        <div><strong>{proposalTitle(call.tool_name)}</strong><code>{call.tool_name}</code></div>
        {call.status === "proposed" ? (
          <button aria-label={`编辑 ${call.tool_name} 参数`} onClick={() => setEditing((value) => !value)}>
            <Pencil size={14} />
          </button>
        ) : resourceHref && call.result_resource_id ? (
          <a href={resourceHref}><ExternalLink size={14} />查看结果</a>
        ) : null}
      </header>
      {editing ? (
        <div className="assistant-proposal__editor">
          <textarea
            aria-label={`${call.tool_name} 参数 JSON`}
            onChange={(event) => { setJsonValue(event.target.value); setError(null); }}
            rows={12}
            spellCheck={false}
            value={jsonValue}
          />
          {error ? <p>{error}</p> : null}
          <div>
            <Button onClick={() => setEditing(false)} size="sm">取消</Button>
            <Button
              onClick={async () => {
                try {
                  const parsed = JSON.parse(jsonValue) as unknown;
                  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
                    throw new Error("参数必须是 JSON 对象");
                  }
                  await onUpdate(parsed as Record<string, unknown>);
                  setEditing(false);
                } catch (value) {
                  setError(value instanceof Error ? value.message : "JSON 格式无效");
                }
              }}
              size="sm"
              variant="primary"
            >保存参数</Button>
          </div>
        </div>
      ) : (
        <>
          <dl>{details.map(([term, value]) => <div key={term}><dt>{term}</dt><dd>{value}</dd></div>)}</dl>
          {cleaningOperations.length ? (
            <ol className="assistant-proposal__operations">
              {cleaningOperations.map((item, index) => {
                const operation = item && typeof item === "object" ? item as Record<string, unknown> : {};
                return (
                  <li key={`${String(operation.operation ?? "operation")}-${index}`}>
                    <span>{index + 1}</span>
                    <div>
                      <strong>{String(operation.operation ?? "-").replaceAll("_", " ")}</strong>
                      <small>{String(operation.column ?? "全表")}</small>
                    </div>
                    <b className={`risk risk--${String(operation.risk_level ?? "low")}`}>
                      {String(operation.risk_level ?? "low")} risk
                    </b>
                  </li>
                );
              })}
            </ol>
          ) : null}
        </>
      )}
    </section>
  );
}

function proposalTitle(toolName: string): string {
  return ({
    "analysis.draft_spec": "分析规格",
    "analysis.run": "分析运行",
    "cleaning.draft_plan": "清洗计划",
    "cleaning.execute": "清洗执行",
    "feature_engineering.suggest": "特征工程建议",
  } as Record<string, string>)[toolName] ?? "受控工具";
}

function proposalDetails(call: AssistantToolCall): Array<[string, string]> {
  const args = call.arguments;
  if (call.tool_name === "analysis.draft_spec") {
    return [
      ["任务", String(args.task ?? "-").replaceAll("_", " ")],
      ["目标", String(args.target ?? "无")],
      ["拆分", String(args.split_strategy ?? "-")],
      ["指标", Array.isArray(args.metrics) ? args.metrics.join(" · ") : "-"],
      ["特征", Array.isArray(args.included_columns) ? `${args.included_columns.length} 个已选字段` : "自动选择"],
    ];
  }
  if (call.tool_name === "cleaning.draft_plan") {
    const operations = Array.isArray(args.operations) ? args.operations : [];
    const highRisk = operations.filter((item) => {
      const value = item && typeof item === "object" ? item as Record<string, unknown> : {};
      return value.risk_level === "high";
    }).length;
    return [["名称", String(args.name ?? "清洗计划")], ["操作", `${operations.length} 步`], ["高风险", `${highRisk} 步`]];
  }
  if (call.tool_name === "feature_engineering.suggest") {
    return [["建议", `${Array.isArray(args.suggestions) ? args.suggestions.length : 0} 项`], ["执行代码", "不会生成"]];
  }
  return Object.entries(args).slice(0, 5).map(([key, value]) => [key, typeof value === "object" ? JSON.stringify(value) : String(value)]);
}

function CitationDrawer({
  projectId,
  citationId,
  onClose,
}: {
  projectId: string;
  citationId: string;
  onClose: () => void;
}) {
  const isArtifact = citationId.startsWith("art_");
  const artifactQuery = useQuery({
    queryKey: ["assistant", "citation", "artifact", citationId],
    queryFn: () => apiClient.getArtifact(projectId, citationId),
    enabled: isArtifact,
  });
  const claimQuery = useQuery({
    queryKey: ["assistant", "citation", "claim", citationId],
    queryFn: () => apiClient.getClaim(projectId, citationId),
    enabled: !isArtifact,
  });
  const value = isArtifact ? artifactQuery.data : claimQuery.data;
  const loading = isArtifact ? artifactQuery.isLoading : claimQuery.isLoading;
  return (
    <aside className="assistant-citation-drawer">
      <header>
        <div><FileSearch size={17} /><h2>证据详情</h2></div>
        <button aria-label="关闭证据" className="icon-button" onClick={onClose}><X size={18} /></button>
      </header>
      <strong>{citationId}</strong>
      {loading ? <LoadingBlock rows={4} /> : null}
      {value ? <pre>{JSON.stringify(value, null, 2)}</pre> : null}
    </aside>
  );
}
