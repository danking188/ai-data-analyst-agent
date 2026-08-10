import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Bot,
  ChevronDown,
  Database,
  FileBarChart,
  Gauge,
  LogOut,
  Menu,
  Plus,
  Search,
  ShieldCheck,
  UploadCloud,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { apiClient } from "../../api/client";
import { useAppContext } from "../../context/AppContext";
import { useAuth } from "../../context/AuthContext";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "../ui/Button";
import { CreateProjectModal } from "../../features/projects/CreateProjectModal";
import { UploadDatasetModal } from "../../features/data/UploadDatasetModal";

const navigation = [
  { to: "/", label: "概览", icon: Gauge },
  { to: "/data", label: "数据", icon: Database },
  { to: "/quality", label: "质量", icon: ShieldCheck },
  { to: "/explore", label: "探索", icon: Search },
  { to: "/model", label: "模型", icon: Bot },
  { to: "/assistant", label: "助手", icon: Bot },
  { to: "/report", label: "报告", icon: FileBarChart },
];

export function AppShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const location = useLocation();
  const { project, dataset, version, setProject, setDataset, setVersion } = useAppContext();

  const projectsQuery = useQuery({
    queryKey: queryKeys.projects,
    queryFn: apiClient.listProjects,
  });
  const datasetsQuery = useQuery({
    queryKey: queryKeys.datasets(project?.project_id ?? "none"),
    queryFn: () => apiClient.listDatasets(project!.project_id),
    enabled: Boolean(project),
  });
  const versionsQuery = useQuery({
    queryKey: queryKeys.versions(project?.project_id ?? "none", dataset?.dataset_id ?? "none"),
    queryFn: () => apiClient.listDatasetVersions(project!.project_id, dataset!.dataset_id),
    enabled: Boolean(project && dataset),
  });
  const capabilitiesQuery = useQuery({
    queryKey: ["system", "capabilities"],
    queryFn: apiClient.getCapabilities,
  });

  useEffect(() => {
    if (!project && projectsQuery.data?.items[0]) setProject(projectsQuery.data.items[0]);
  }, [project, projectsQuery.data, setProject]);

  useEffect(() => {
    if (!dataset && datasetsQuery.data?.items[0]) setDataset(datasetsQuery.data.items[0]);
  }, [dataset, datasetsQuery.data, setDataset]);

  useEffect(() => {
    if (!version && versionsQuery.data?.items[0]) setVersion(versionsQuery.data.items[0]);
  }, [setVersion, version, versionsQuery.data]);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  const nav = (
    <>
      <div className="brand">
        <span className="brand__mark" aria-hidden="true">
          <BarChart3 size={22} />
        </span>
        <span>DataTrace</span>
      </div>
      <nav aria-label="主导航" className="sidebar__nav">
        {navigation.filter(({ to }) => to !== "/assistant" || capabilitiesQuery.data?.llm.assistant !== false).map(({ to, label, icon: Icon }) => (
          <NavLink className={({ isActive }) => `nav-item ${isActive ? "is-active" : ""}`} end={to === "/"} key={to} to={to}>
            <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar__context">
        <button className="context-card" onClick={() => setProjectModalOpen(true)}>
          <span className="context-card__label">当前项目</span>
          <strong>{project?.name ?? "选择项目"}</strong>
          <span className="context-card__version">
            <i />
            {version ? `v${version.version_number} · ${version.kind}` : "尚无数据版本"}
          </span>
          <ChevronDown aria-hidden="true" size={16} />
        </button>
        <div className="user-row">
          <span className="avatar">DA</span>
          <span className="user-row__identity">
            <strong>{auth?.session.subject_id ?? "Data Analyst"}</strong>
            <small>{apiClient.mode === "mock" ? "Mock workspace" : "Connected"}</small>
          </span>
          {auth ? <button aria-label="退出登录" className="icon-button" onClick={auth.logout} title="退出登录"><LogOut size={16} /></button> : null}
        </div>
      </div>
    </>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">{nav}</aside>
      {mobileOpen ? (
        <div className="mobile-nav-backdrop" onClick={() => setMobileOpen(false)}>
          <aside className="mobile-nav" onClick={(event) => event.stopPropagation()}>
            <button aria-label="关闭导航" className="icon-button mobile-nav__close" onClick={() => setMobileOpen(false)}>
              <X size={20} />
            </button>
            {nav}
          </aside>
        </div>
      ) : null}
      <div className="app-main">
        <header className="topbar">
          <button aria-label="打开导航" className="icon-button mobile-menu" onClick={() => setMobileOpen(true)}>
            <Menu size={20} />
          </button>
          <button className="topbar__project" onClick={() => setProjectModalOpen(true)}>
            <span>{project?.name ?? "正在载入项目"}</span>
            <ChevronDown size={15} />
          </button>
          <select
            aria-label="当前数据版本"
            className="topbar__version"
            disabled={!version}
            onChange={(event) => {
              const selected = versionsQuery.data?.items.find((item) => item.version_id === event.target.value);
              if (selected) setVersion(selected);
            }}
            value={version?.version_id ?? ""}
          >
            {!version ? <option value="">无数据版本</option> : null}
            {versionsQuery.data?.items.map((item) => (
              <option key={item.version_id} value={item.version_id}>v{item.version_number} · {item.kind}</option>
            ))}
          </select>
          <div className="topbar__actions">
            <Button
              aria-label="上传数据"
              disabled={!project}
              icon={<UploadCloud size={17} />}
              onClick={() => setUploadModalOpen(true)}
              variant="primary"
            >
              上传数据
            </Button>
            <Button aria-label="新建项目" icon={<Plus size={17} />} onClick={() => setProjectModalOpen(true)}>
              新建项目
            </Button>
          </div>
        </header>
        <main className="page">{children}</main>
      </div>
      <CreateProjectModal open={projectModalOpen} onClose={() => setProjectModalOpen(false)} />
      <UploadDatasetModal open={uploadModalOpen} onClose={() => setUploadModalOpen(false)} />
    </div>
  );
}
