import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import App from "./App";
import { ToastProvider } from "./components/ui/ToastProvider";
import { AppProvider } from "./context/AppContext";

describe("App", () => {
  it("renders the overview workspace in mock mode", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/"]}>
          <ToastProvider>
            <AppProvider>
              <App />
            </AppProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "分析工作台" })).toBeInTheDocument();
    expect(await screen.findByText("customer_churn.xlsx")).toBeInTheDocument();
    expect(await screen.findByText("数据质量总览")).toBeInTheDocument();
  });

  it.each([
    ["/quality/cleaning", "清洗计划"],
    ["/explore", "分析设计"],
    ["/model", "模型评估"],
    ["/report", "分析报告"],
    ["/assistant", "AI 分析助手"],
  ])("renders the completed workflow at %s", async (route, heading) => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>
          <ToastProvider>
            <AppProvider>
              <App />
            </AppProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it("renders cleaning controls from schema and version data", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/quality/cleaning"]}>
          <ToastProvider>
            <AppProvider>
              <App />
            </AppProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect((await screen.findAllByRole("option", { name: "customer_id" })).length).toBeGreaterThan(0);
    const resultSection = screen.getByRole("heading", { name: "执行与结果" }).closest("section");
    expect(resultSection).not.toBeNull();
    expect(within(resultSection!).getByText("v3")).toBeInTheDocument();
    expect(within(resultSection!).getByText("82,310 行")).toBeInTheDocument();
    expect(screen.queryByText("CUST-001")).not.toBeInTheDocument();
    expect(screen.getByText("生成预览后显示真实样本差异。")).toBeInTheDocument();
  });

  it("shows evidence narrative action when the deployment enables LLM", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/report"]}>
          <ToastProvider>
            <AppProvider>
              <App />
            </AppProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("button", { name: "AI 解读" })).toBeInTheDocument();
  });

  it("renders assistant evidence, tool activity, and confirmation controls", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/assistant"]}>
          <ToastProvider>
            <AppProvider>
              <App />
            </AppProvider>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("客户流失与数据质量")).toBeInTheDocument();
    expect(await screen.findByText("claim.search")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "确认执行" })).toBeInTheDocument();
    expect((await screen.findAllByRole("button", { name: /claim_/ })).length).toBeGreaterThan(0);
    expect(await screen.findByText("churned")).toBeInTheDocument();
    expect(await screen.findByText("f1 · roc_auc · pr_auc")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "编辑 analysis.draft_spec 参数" })).toBeInTheDocument();
  });
});
