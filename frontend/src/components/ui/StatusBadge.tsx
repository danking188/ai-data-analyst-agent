import {
  Ban,
  CheckCircle2,
  CircleAlert,
  Clock3,
  LoaderCircle,
  ShieldAlert,
} from "lucide-react";

const statusMap = {
  succeeded: { label: "成功", tone: "success", icon: CheckCircle2 },
  ready: { label: "可用", tone: "success", icon: CheckCircle2 },
  active: { label: "正常", tone: "success", icon: CheckCircle2 },
  resolved: { label: "已解决", tone: "success", icon: CheckCircle2 },
  running: { label: "运行中", tone: "warning", icon: LoaderCircle },
  queued: { label: "排队中", tone: "neutral", icon: Clock3 },
  creating: { label: "创建中", tone: "neutral", icon: LoaderCircle },
  open: { label: "待处理", tone: "warning", icon: CircleAlert },
  accepted: { label: "已接受", tone: "info", icon: CheckCircle2 },
  ignored: { label: "已忽略", tone: "neutral", icon: Ban },
  failed: { label: "失败", tone: "danger", icon: CircleAlert },
  blocked: { label: "已阻断", tone: "danger", icon: ShieldAlert },
  cancelled: { label: "已取消", tone: "neutral", icon: Ban },
  archived: { label: "已归档", tone: "neutral", icon: Ban },
} as const;

export function StatusBadge({ status }: { status: string }) {
  const config = statusMap[status as keyof typeof statusMap] ?? {
    label: status,
    tone: "neutral",
    icon: Clock3,
  };
  const Icon = config.icon;
  return (
    <span className={`status status--${config.tone}`}>
      <Icon aria-hidden="true" size={14} />
      {config.label}
    </span>
  );
}
