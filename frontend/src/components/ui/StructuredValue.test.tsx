import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { formatScalar, StructuredValue } from "./StructuredValue";

describe("formatScalar", () => {
  it.each([
    [12.5, "12.5"],
    [true, "是"],
    [false, "否"],
    [null, "-"],
    [undefined, "-"],
    ["drop_duplicates", "drop duplicates"],
  ])("renders %s as %s", (value, expected) => {
    expect(formatScalar(value)).toBe(expected);
  });
});

describe("StructuredValue", () => {
  it("renders a confusion matrix as a labelled table", () => {
    render(<StructuredValue value={{ labels: ["no", "yes"], values: [[4, 1], [2, 8]] }} />);
    expect(screen.getByText("实际 \\ 预测")).toBeInTheDocument();
    expect(screen.queryByText(/object Object/)).not.toBeInTheDocument();
    const table = screen.getByRole("table");
    // Column headers are the predicted labels, row headers the actual ones.
    expect([...table.querySelectorAll("thead th")].map((cell) => cell.textContent)).toEqual([
      "实际 \\ 预测",
      "no",
      "yes",
    ]);
    expect([...table.querySelectorAll("tbody tr")].map((row) => [...row.children].map((cell) => cell.textContent))).toEqual([
      ["no", "4", "1"],
      ["yes", "2", "8"],
    ]);
  });

  it("renders an array of flat records as a table", () => {
    render(
      <StructuredValue
        value={[
          { model: "logistic_regression", f1: 0.81 },
          { model: "random_forest", f1: 0.86 },
        ]}
      />,
    );
    const table = screen.getByRole("table");
    expect([...table.querySelectorAll("thead th")].map((cell) => cell.textContent)).toEqual(["model", "f1"]);
    expect(screen.getByText("logistic regression")).toBeInTheDocument();
    expect(screen.getByText("0.86")).toBeInTheDocument();
  });

  it("renders a scalar array as a separated list", () => {
    render(<StructuredValue value={["amount", "balance"]} />);
    expect(screen.getByText("amount、balance")).toBeInTheDocument();
  });

  it("never stringifies a nested object", () => {
    render(
      <StructuredValue
        value={{ baseline_metrics: { accuracy: 0.9 }, residual_summary: { mean: -0.01, p95: 1.2 } }}
      />,
    );
    expect(screen.queryByText(/object Object/)).not.toBeInTheDocument();
    expect(screen.getByText("baseline metrics")).toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(3);
    expect(screen.getByText("-0.01")).toBeInTheDocument();
  });

  it("does not treat a non-square labels/values object as a confusion matrix", () => {
    // Three count rows for two labels is not the evaluation payload shape, so it must fall
    // back to the generic key/value rendering instead of mislabelling the grid.
    render(<StructuredValue value={{ labels: ["no", "yes"], values: [[4, 1], [2, 8], [1, 1]] }} />);
    expect(screen.queryByText("实际 \\ 预测")).not.toBeInTheDocument();
    expect(screen.getByText("labels")).toBeInTheDocument();
  });
});
