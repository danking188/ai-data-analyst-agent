import type { ErrorDetail } from "./contracts";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: ErrorDetail;

  constructor(status: number, detail: ErrorDetail) {
    super(detail.message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  return new ApiError(500, {
    code: "NETWORK_ERROR",
    message: error instanceof Error ? error.message : "网络请求失败，请稍后重试",
    request_id: "req_client",
    retryable: true,
    details: {},
  });
}
