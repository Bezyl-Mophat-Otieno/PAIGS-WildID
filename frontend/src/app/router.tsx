import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/app-shell"
import { AdminRoute, ProtectedRoute } from "@/app/protected-route"
import { ConfigurationPage } from "@/pages/configuration/configuration-page"
import { DashboardPage } from "@/pages/dashboard/dashboard-page"
import { LoginPage } from "@/pages/login/login-page"
import { NewAnalysisPage } from "@/pages/new-analysis/new-analysis-page"
import { ReferenceDatabasePage } from "@/pages/reference-database/reference-database-page"
import { ReportsPage } from "@/pages/reports/reports-page"
import { RerunPage } from "@/pages/rerun/rerun-page"
import { RunDetailPage } from "@/pages/run-detail/run-detail-page"
import { RunHistoryPage } from "@/pages/run-history/run-history-page"
import { TeamPage } from "@/pages/team/team-page"

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route
          element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/new-analysis" element={<NewAnalysisPage />} />
          <Route path="/runs" element={<RunHistoryPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
          <Route path="/runs/:runId/rerun" element={<RerunPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/configuration" element={<ConfigurationPage />} />
          <Route path="/reference-database" element={<ReferenceDatabasePage />} />
          <Route
            path="/team"
            element={
              <AdminRoute>
                <TeamPage />
              </AdminRoute>
            }
          />
        </Route>

        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
