import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Dataset, DatasetVersion, Project } from "../api/contracts";

interface AppSelection {
  project: Project | null;
  dataset: Dataset | null;
  version: DatasetVersion | null;
}

interface AppContextValue extends AppSelection {
  setProject: (project: Project | null) => void;
  setDataset: (dataset: Dataset | null) => void;
  setVersion: (version: DatasetVersion | null) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [project, setProjectState] = useState<Project | null>(null);
  const [dataset, setDatasetState] = useState<Dataset | null>(null);
  const [version, setVersion] = useState<DatasetVersion | null>(null);
  const setProject = useCallback((nextProject: Project | null) => {
    setProjectState(nextProject);
    setDatasetState(null);
    setVersion(null);
  }, []);
  const setDataset = useCallback((nextDataset: Dataset | null) => {
    setDatasetState(nextDataset);
    setVersion(null);
  }, []);

  const value = useMemo(
    () => ({ project, dataset, version, setProject, setDataset, setVersion }),
    [dataset, project, setDataset, setProject, version],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useAppContext must be used inside AppProvider");
  return value;
}
