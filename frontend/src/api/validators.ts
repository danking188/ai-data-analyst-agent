import { z } from "zod";

const errorDetailSchema = z.object({
  code: z.string(),
  message: z.string(),
  request_id: z.string(),
  retryable: z.boolean(),
  details: z.record(z.unknown()),
});

export const projectSchema = z.object({
  project_id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  timezone: z.string(),
  language: z.enum(["zh-CN", "en-US"]),
  status: z.enum(["active", "archived"]),
  current_dataset_version_id: z.string().nullable(),
  revision: z.number().int().min(1),
  created_at: z.string(),
  updated_at: z.string(),
});

export const projectPageSchema = z.object({
  items: z.array(projectSchema),
  page: z.number().int().min(1),
  page_size: z.number().int().min(1),
  total: z.number().int().min(0),
  has_more: z.boolean(),
});

export const jobSchema = z.object({
  job_id: z.string(),
  kind: z.enum([
    "dataset_ingestion",
    "version_comparison",
    "quality_scan",
    "cleaning_preview",
    "cleaning_execute",
    "analysis_run",
    "report_export",
    "assistant_turn",
  ]),
  status: z.enum(["queued", "running", "cancelling", "cancelled", "blocked", "succeeded", "failed"]),
  progress: z.number().int().min(0).max(100),
  current_step: z.string().nullable(),
  resource_type: z.string().nullable(),
  resource_id: z.string().nullable(),
  retry_after_ms: z.number().int().min(0).nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  error: errorDetailSchema.nullable(),
});
