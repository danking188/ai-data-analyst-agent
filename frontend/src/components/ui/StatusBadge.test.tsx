import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each([
    ["succeeded", "成功"],
    ["processing", "处理中"],
    ["completed", "已完成"],
    ["awaiting_confirmation", "待确认"],
    ["approved", "已批准"],
    ["rejected", "已拒绝"],
  ])("localizes the %s status", (status, label) => {
    render(<StatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
