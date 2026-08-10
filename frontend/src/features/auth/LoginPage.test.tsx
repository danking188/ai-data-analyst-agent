import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

function renderPage(overrides: Partial<ComponentProps<typeof LoginPage>> = {}) {
  const props: ComponentProps<typeof LoginPage> = {
    loginError: null,
    registerError: null,
    loading: false,
    registrationEnabled: true,
    onLogin: vi.fn(),
    onRegister: vi.fn(),
    ...overrides,
  };
  render(<LoginPage {...props} />);
  return props;
}

describe("LoginPage", () => {
  it("submits existing account credentials", () => {
    const props = renderPage();
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "analyst" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "test-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(props.onLogin).toHaveBeenCalledWith("analyst", "test-password");
  });

  it("validates password confirmation before registration", () => {
    const props = renderPage();
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "new-user" } });
    fireEvent.change(screen.getByLabelText("密码"), {
      target: { value: "safe-password-2026" },
    });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "different-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));
    expect(screen.getByRole("alert")).toHaveTextContent("两次输入的密码不一致");
    expect(props.onRegister).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "safe-password-2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));
    expect(props.onRegister).toHaveBeenCalledWith("new-user", "safe-password-2026");
  });

  it("hides self-service registration when the deployment disables it", () => {
    renderPage({ registrationEnabled: false });
    expect(screen.queryByRole("tab", { name: "注册" })).not.toBeInTheDocument();
  });
});
