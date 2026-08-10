#!/usr/bin/env bash
set -euo pipefail

: "${S3_BUCKET:?S3_BUCKET is required}"

args=(s3api get-bucket-versioning --bucket "$S3_BUCKET")
if [[ -n "${S3_ENDPOINT_URL:-}" ]]; then
  args+=(--endpoint-url "$S3_ENDPOINT_URL")
fi
status="$(aws "${args[@]}" --query Status --output text)"
if [[ "$status" != "Enabled" ]]; then
  printf 'Bucket versioning is not enabled for %s (status: %s).\n' "$S3_BUCKET" "$status" >&2
  exit 1
fi
printf 'Bucket versioning is enabled for %s.\n' "$S3_BUCKET"
