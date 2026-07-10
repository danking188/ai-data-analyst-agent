import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { apiClient } from "../api/client";
import type { Job } from "../api/contracts";
import { queryKeys } from "../lib/queryKeys";

const terminalStatuses = new Set<Job["status"]>([
  "succeeded",
  "failed",
  "cancelled",
  "blocked",
]);

export function useJobPolling(jobId: string | null, onSuccess?: (job: Job) => void) {
  const queryClient = useQueryClient();
  const notifiedJobId = useRef<string | null>(null);
  const query = useQuery({
    queryKey: queryKeys.job(jobId ?? "none"),
    queryFn: () => apiClient.getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (state) => {
      const job = state.state.data;
      if (!job || terminalStatuses.has(job.status)) return false;
      if (document.visibilityState === "hidden") return 10_000;
      const age = Date.now() - new Date(job.created_at).getTime();
      return job.retry_after_ms ?? (age < 30_000 ? 1_000 : 3_000);
    },
  });

  const job = query.data;
  useEffect(() => {
    if (job?.status !== "succeeded" || !onSuccess || notifiedJobId.current === job.job_id) return;
    notifiedJobId.current = job.job_id;
    onSuccess(job);
  }, [job, onSuccess]);

  const cancelMutation = useMutation({
    mutationFn: () => apiClient.cancelJob(jobId as string),
    onSuccess: (nextJob) => {
      queryClient.setQueryData(queryKeys.job(nextJob.job_id), nextJob);
    },
  });

  return {
    ...query,
    job,
    isTerminal: job ? terminalStatuses.has(job.status) : false,
    cancel: cancelMutation.mutate,
    isCancelling: cancelMutation.isPending,
  };
}
