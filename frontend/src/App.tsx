import type { ReactNode } from "react";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { config } from "./config";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <main className="card muted">Loading…</main>;
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

function GoogleWrapper({ children }: { children: ReactNode }) {
  if (!config.googleClientId) return children;
  return <GoogleOAuthProvider clientId={config.googleClientId}>{children}</GoogleOAuthProvider>;
}

export default function App() {
  return (
    <GoogleWrapper>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <RequireAuth>
                  <ProfilePage />
                </RequireAuth>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </GoogleWrapper>
  );
}
