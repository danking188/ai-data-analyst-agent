import { ArrowRight, Construction, DatabaseZap } from "lucide-react";
import { Link } from "react-router-dom";

const copy = {
  explore: {
    title: "探索与分析",
    description: "确认分析目标后，系统将生成结构化计划并调用确定性工具。",
    action: "查看数据质量",
    to: "/quality",
  },
  model: {
    title: "Baseline 建模",
    description: "选择目标字段、预测时点和拆分策略后，才能启动无泄露的模型评估。",
    action: "检查字段 Schema",
    to: "/data",
  },
  report: {
    title: "报告与证据",
    description: "只有通过验证并绑定 Artifact 的 Claim 才能进入正式报告。",
    action: "返回分析工作台",
    to: "/",
  },
};

export function WorkflowPlaceholder({ kind }: { kind: keyof typeof copy }) {
  const content = copy[kind];
  return (
    <div className="workflow-placeholder">
      <span className="workflow-placeholder__icon">{kind === "report" ? <DatabaseZap size={30} /> : <Construction size={30} />}</span>
      <h1>{content.title}</h1>
      <p>{content.description}</p>
      <div className="workflow-steps">
        <span className="is-complete">数据版本</span><ArrowRight size={15} />
        <span className="is-complete">Schema 与质量</span><ArrowRight size={15} />
        <span>AnalysisSpec</span><ArrowRight size={15} />
        <span>运行与证据</span>
      </div>
      <Link className="button button--primary button--md" to={content.to}>{content.action}</Link>
    </div>
  );
}
