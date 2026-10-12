/** Formats the scalar values the report and artifact viewers display. */
export function formatScalar(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    return value.toLocaleString("zh-CN", { maximumFractionDigits: 6 });
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string") return value.replaceAll("_", " ");
  return "-";
}

type ConfusionMatrix = { labels: string[]; values: number[][] };

/** Model evaluation artifacts store a confusion matrix as labels plus a square count grid. */
function asConfusionMatrix(value: unknown): ConfusionMatrix | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Record<string, unknown>;
  const { labels, values } = candidate;
  if (!Array.isArray(labels) || !labels.every((label) => typeof label === "string")) return null;
  if (!Array.isArray(values) || !values.length) return null;
  const rows = values.filter(
    (row): row is number[] => Array.isArray(row) && row.every((cell) => typeof cell === "number"),
  );
  if (rows.length !== labels.length) return null;
  if (!rows.every((row) => row.length === labels.length)) return null;
  return { labels, values: rows };
}

function isScalar(value: unknown): boolean {
  return value === null || value === undefined || typeof value !== "object";
}

/** True for arrays like `comparison` or `feature_importance`: every row is a flat record. */
function asFlatRows(value: unknown): Array<Record<string, unknown>> | null {
  if (!Array.isArray(value) || !value.length) return null;
  const rows = value.filter(
    (row): row is Record<string, unknown> =>
      Boolean(row) && typeof row === "object" && !Array.isArray(row),
  );
  if (rows.length !== value.length) return null;
  if (!rows.every((row) => Object.values(row).every(isScalar))) return null;
  return rows;
}

function keyLabel(key: string): string {
  return key.replaceAll("_", " ");
}

function RowTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  return (
    <div className="artifact-table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{keyLabel(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{formatScalar(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConfusionMatrixTable({ matrix }: { matrix: ConfusionMatrix }) {
  return (
    <div className="artifact-table-wrap">
      <table>
        <thead>
          <tr>
            <th>实际 \ 预测</th>
            {matrix.labels.map((label) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.values.map((row, rowIndex) => (
            <tr key={matrix.labels[rowIndex]}>
              <th>{matrix.labels[rowIndex]}</th>
              {row.map((cell, columnIndex) => (
                <td key={matrix.labels[columnIndex]}>{formatScalar(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Renders an artifact value of any shape without ever stringifying an object.
 *
 * Confusion matrices and arrays of rows become tables, other objects become key/value rows,
 * and scalars keep the formatting used across the report pages.
 */
export function StructuredValue({ value }: { value: unknown }) {
  const matrix = asConfusionMatrix(value);
  if (matrix) return <ConfusionMatrixTable matrix={matrix} />;

  const rows = asFlatRows(value);
  if (rows) return <RowTable rows={rows} />;

  if (Array.isArray(value)) {
    return <>{value.map((item) => formatScalar(item)).join("、")}</>;
  }

  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return <>-</>;
    return (
      <table>
        <tbody>
          {entries.map(([key, item]) => (
            <tr key={key}>
              <th>{keyLabel(key)}</th>
              <td>
                <StructuredValue value={item} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  return <>{formatScalar(value)}</>;
}
