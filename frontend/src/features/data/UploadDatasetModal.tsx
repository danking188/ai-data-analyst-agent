import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, UploadCloud, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiClient } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useToast } from "../../components/ui/ToastProvider";
import { useAppContext } from "../../context/AppContext";
import { useJobPolling } from "../../hooks/useJobPolling";
import { fileSize } from "../../lib/format";
import { queryKeys } from "../../lib/queryKeys";

const acceptedExtensions = [".csv", ".xls", ".xlsx", ".parquet"];
function validateFile(file: File, maxBytes: number) {
  const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
  if (!acceptedExtensions.includes(extension)) return "仅支持 CSV、XLS、XLSX 和 Parquet";
  if (file.size > maxBytes) return `文件超过 ${fileSize(maxBytes)} 限制`;
  if (file.size === 0) return "文件为空，请重新选择";
  return null;
}

export function UploadDatasetModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(() => sessionStorage.getItem("active-upload-job"));
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { project, dataset } = useAppContext();
  const capabilitiesQuery = useQuery({
    queryKey: ["system", "capabilities"],
    queryFn: apiClient.getCapabilities,
    enabled: open,
  });
  const maxBytes = capabilitiesQuery.data?.max_upload_bytes ?? 104_857_600;

  const reset = () => {
    setFile(null);
    setDatasetName("");
    setValidationError(null);
    setJobId(null);
    sessionStorage.removeItem("active-upload-job");
  };

  const mutation = useMutation({
    mutationFn: () => apiClient.uploadDataset(project!.project_id, file!, datasetName.trim()),
    onSuccess: (job) => {
      setJobId(job.job_id);
      sessionStorage.setItem("active-upload-job", job.job_id);
    },
  });

  const polling = useJobPolling(jobId, () => {
    if (!project) return;
    queryClient.invalidateQueries({ queryKey: queryKeys.datasets(project.project_id) });
    if (dataset) {
      queryClient.invalidateQueries({ queryKey: queryKeys.versions(project.project_id, dataset.dataset_id) });
    }
    pushToast("数据上传与解析已完成");
  });

  useEffect(() => {
    if (!open && polling.job?.status === "succeeded") reset();
  }, [open, polling.job?.status]);

  const selectFile = (nextFile: File | null) => {
    if (!nextFile) {
      setFile(null);
      setDatasetName("");
      setValidationError(null);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    const error = validateFile(nextFile, maxBytes);
    setValidationError(error);
    if (error) {
      setFile(null);
      return;
    }
    setFile(nextFile);
    setDatasetName(nextFile.name.replace(/\.[^.]+$/, ""));
  };

  const close = () => {
    if (mutation.isPending) return;
    if (polling.job && !polling.isTerminal) {
      onClose();
      return;
    }
    reset();
    onClose();
  };

  return (
    <Modal
      footer={
        polling.job ? (
          <>
            {!polling.isTerminal ? (
              <Button disabled={polling.isCancelling} onClick={() => polling.cancel()} variant="danger">
                {polling.isCancelling ? "正在取消…" : "取消任务"}
              </Button>
            ) : null}
            <Button disabled={!polling.isTerminal} onClick={close} variant="primary">
              完成
            </Button>
          </>
        ) : (
          <>
            <Button disabled={mutation.isPending} onClick={close}>取消</Button>
            <Button
              disabled={!file || !datasetName.trim() || mutation.isPending || !project}
              onClick={() => mutation.mutate()}
              variant="primary"
            >
              {mutation.isPending ? "正在提交…" : "开始上传"}
            </Button>
          </>
        )
      }
      onClose={close}
      open={open}
      title="上传数据"
    >
      {polling.job ? (
        <div className="job-progress" role="status">
          <div className="job-progress__top">
            <span>
              <strong>{polling.job.status === "succeeded" ? "上传与解析完成" : "正在创建数据版本"}</strong>
              <small>{polling.job.current_step ?? "任务已进入终态"}</small>
            </span>
            <b>{polling.job.progress}%</b>
          </div>
          <div className="progress-track"><i style={{ width: `${polling.job.progress}%` }} /></div>
          <p>任务 ID：{polling.job.job_id}</p>
          {polling.job.status === "cancelled" ? <p className="form-error">任务已取消，不会生成可用版本。</p> : null}
          {polling.job.error ? <p className="form-error">{polling.job.error.message}</p> : null}
        </div>
      ) : (
        <div className="form-stack">
          <input
            accept={acceptedExtensions.join(",")}
            className="sr-only"
            onChange={(event) => selectFile(event.target.files?.[0] ?? null)}
            ref={inputRef}
            type="file"
          />
          <button
            className="dropzone"
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              selectFile(event.dataTransfer.files[0] ?? null);
            }}
          >
            <UploadCloud aria-hidden="true" size={34} />
            <strong>将文件拖到此处，或点击选择文件</strong>
            <span>支持 CSV、XLS、XLSX、Parquet，最大 {fileSize(maxBytes)}</span>
          </button>
          <label className="field">
            <span>数据集名称</span>
            <input
              disabled={!file}
              maxLength={120}
              onChange={(event) => setDatasetName(event.target.value)}
              placeholder="选择文件后自动填写"
              value={datasetName}
            />
          </label>
          {file ? (
            <div className="selected-file">
              <FileSpreadsheet aria-hidden="true" size={22} />
              <span><strong>{file.name}</strong><small>{fileSize(file.size)}</small></span>
              <button aria-label="移除文件" className="icon-button" onClick={() => selectFile(null)}>
                <X size={16} />
              </button>
            </div>
          ) : null}
          {validationError || mutation.error ? (
            <p className="form-error">{validationError ?? mutation.error?.message}</p>
          ) : null}
        </div>
      )}
    </Modal>
  );
}
