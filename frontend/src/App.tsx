import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { LoadingBlock } from "./components/ui/LoadingBlock";

const OverviewPage = lazy(() => import("./features/overview/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const DataPage = lazy(() => import("./features/data/DataPage").then((module) => ({ default: module.DataPage })));
const CleaningPage = lazy(() => import("./features/cleaning/CleaningPage").then((module) => ({ default: module.CleaningPage })));
const ExplorePage = lazy(() => import("./features/explore/ExplorePage").then((module) => ({ default: module.ExplorePage })));
const ModelPage = lazy(() => import("./features/model/ModelPage").then((module) => ({ default: module.ModelPage })));
const QualityPage = lazy(() => import("./features/quality/QualityPage").then((module) => ({ default: module.QualityPage })));
const ReportPage = lazy(() => import("./features/report/ReportPage").then((module) => ({ default: module.ReportPage })));
const AssistantPage = lazy(() => import("./features/assistant/AssistantPage").then((module) => ({ default: module.AssistantPage })));

export default function App() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingBlock rows={8} />}>
        <Routes>
          <Route element={<OverviewPage />} path="/" />
          <Route element={<DataPage />} path="/data" />
          <Route element={<QualityPage />} path="/quality" />
          <Route element={<CleaningPage />} path="/quality/cleaning" />
          <Route element={<ExplorePage />} path="/explore" />
          <Route element={<ModelPage />} path="/model" />
          <Route element={<ReportPage />} path="/report" />
          <Route element={<AssistantPage />} path="/assistant" />
          <Route element={<Navigate replace to="/" />} path="*" />
        </Routes>
      </Suspense>
    </AppShell>
  );
}
