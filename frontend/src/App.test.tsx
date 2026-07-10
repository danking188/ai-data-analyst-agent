import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
    ["/model", "基线模型"],
    ["/report", "分析报告"],
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
});
