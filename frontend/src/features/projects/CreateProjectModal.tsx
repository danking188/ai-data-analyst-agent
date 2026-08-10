import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "../../api/client";
import { useAppContext } from "../../context/AppContext";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useToast } from "../../components/ui/ToastProvider";

export function CreateProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const { setProject, setDataset, setVersion } = useAppContext();
  const projectsQuery = useQuery({ queryKey: queryKeys.projects, queryFn: apiClient.listProjects });
  const mutation = useMutation({
    mutationFn: () =>
      apiClient.createProject({
        name: name.trim(),
        description: description.trim() || null,
        timezone: "Asia/Shanghai",
        language: "zh-CN",
      }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      setProject(project);
      setDataset(null);
      setVersion(null);
      setName("");
      setDescription("");
      pushToast("项目已创建");
      onClose();
    },
  });

  const close = () => {
    if (!mutation.isPending) onClose();
  };

  return (
    <Modal
      footer={
        <>
          <Button disabled={mutation.isPending} onClick={close}>取消</Button>
          <Button
            disabled={!name.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
            variant="primary"
          >
            {mutation.isPending ? "正在创建…" : "创建项目"}
          </Button>
        </>
      }
      onClose={close}
      open={open}
      title="选择或新建分析项目"
    >
      <div className="form-stack">
        {projectsQuery.data?.items.length ? (
          <div className="project-picker" aria-label="已有项目">
            {projectsQuery.data.items.map((project) => (
              <button
                className="context-card"
                key={project.project_id}
                onClick={() => {
                  setProject(project);
                  onClose();
                }}
              >
                <strong>{project.name}</strong>
                <span>{project.description || "暂无项目说明"}</span>
              </button>
            ))}
          </div>
        ) : null}
        <h3>新建项目</h3>
        <label className="field">
          <span>项目名称</span>
          <input
            autoFocus
            maxLength={120}
            onChange={(event) => setName(event.target.value)}
            placeholder="例如：客户流失分析"
            value={name}
          />
        </label>
        <label className="field">
          <span>项目说明 <small>可选</small></span>
          <textarea
            maxLength={2000}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="说明数据范围、分析目标或使用限制"
            rows={4}
            value={description}
          />
        </label>
        {mutation.error ? <p className="form-error">{mutation.error.message}</p> : null}
      </div>
    </Modal>
  );
}
