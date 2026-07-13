import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/shell/AppShell";
import { DataPage } from "./features/data/DataPage";
import { CleaningPage } from "./features/cleaning/CleaningPage";
import { ExplorePage } from "./features/explore/ExplorePage";
import { ModelPage } from "./features/model/ModelPage";
import { OverviewPage } from "./features/overview/OverviewPage";
import { QualityPage } from "./features/quality/QualityPage";
import { ReportPage } from "./features/report/ReportPage";
import { AssistantPage } from "./features/assistant/AssistantPage";

export default function App() {
  return (
    <AppShell>
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
    </AppShell>
  );
}
