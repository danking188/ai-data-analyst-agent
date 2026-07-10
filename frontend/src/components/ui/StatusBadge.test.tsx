import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders a localized job status", () => {
    render(<StatusBadge status="succeeded" />);
    expect(screen.getByText("成功")).toBeInTheDocument();
  });
});
