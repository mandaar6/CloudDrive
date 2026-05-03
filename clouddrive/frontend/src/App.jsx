import React, { useState, useEffect, createContext, useContext } from "react";
import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import axios from "axios";

import Login         from "./Login";
import Register      from "./Register";
import Dashboard     from "./Dashboard";
import ResetPassword from "./ResetPassword";

// ── Auth context ──────────────────────────────────────────────────────────────
export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}

const api = axios.create({ baseURL: "/api", withCredentials: true });
export { api };

// ── Email verification page ───────────────────────────────────────────────────
function VerifyEmail() {
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token") || "";
    if (!token) {
      setStatus("error");
      setMessage("Invalid or missing verification token.");
      return;
    }
    api.get(`/auth/verify-email?token=${encodeURIComponent(token)}`)
      .then(res => { setStatus("success"); setMessage(res.data.message); })
      .catch(err => {
        setStatus("error");
        setMessage(err.response?.data?.error || "Verification failed.");
      });
  }, []);

  const cardStyle = {
    display: "flex", alignItems: "center", justifyContent: "center",
    minHeight: "100vh", background: "#f5f7fa",
  };
  const innerStyle = {
    background: "#fff", borderRadius: 12, padding: "2.5rem 2rem",
    boxShadow: "0 4px 24px rgba(0,0,0,.08)", width: "100%", maxWidth: 400,
    textAlign: "center",
  };
  const successStyle = {
    color: "#16a34a", background: "#f0fdf4", border: "1px solid #86efac",
    borderRadius: 8, padding: "12px 16px", marginBottom: 16, fontSize: 14,
  };
  const errorStyle = { color: "#dc2626", marginBottom: 12, fontSize: 13 };

  return (
    <div style={cardStyle}>
      <div style={innerStyle}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Email Verification</h1>
        {status === "loading" && <p>Verifying…</p>}
        {status === "success" && <p style={successStyle}>{message}</p>}
        {status === "error"   && <p style={errorStyle}>{message}</p>}
        {status !== "loading" && (
          <p style={{ fontSize: 13 }}>
            <a href="/login" style={{ color: "#4f46e5" }}>Back to login</a>
          </p>
        )}
      </div>
    </div>
  );
}

// ── Protected route wrapper ───────────────────────────────────────────────────
function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <p style={{ padding: 32 }}>Loading…</p>;
  return user ? children : <Navigate to="/login" replace />;
}

// ── App root ──────────────────────────────────────────────────────────────────
export default function App() {
  const [user, setUser]                   = useState(null);
  const [loading, setLoading]             = useState(true);
  const [activeSection, setActiveSection] = useState("all-files");
  const navigate                          = useNavigate();

  useEffect(() => {
    api.get("/auth/me")
      .then(res => setUser(res.data.user))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    setUser(null);
    navigate("/login");
  };

  return (
    <AuthContext.Provider value={{ user, setUser, loading, logout }}>
      <Routes>
        <Route path="/login"          element={<Login />} />
        <Route path="/register"       element={<Register />} />
        <Route path="/verify-email"   element={<VerifyEmail />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <Dashboard
                activeSection={activeSection}
                setActiveSection={setActiveSection}
              />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthContext.Provider>
  );
}
