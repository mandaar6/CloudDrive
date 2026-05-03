import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api, useAuth } from "./App";

const styles = {
  page: {
    display: "flex", alignItems: "center", justifyContent: "center",
    minHeight: "100vh", background: "#f5f7fa",
  },
  card: {
    background: "#fff", borderRadius: 12, padding: "2.5rem 2rem",
    boxShadow: "0 4px 24px rgba(0,0,0,.08)", width: "100%", maxWidth: 400,
  },
  title: { fontSize: 24, fontWeight: 700, marginBottom: 24, textAlign: "center" },
  label: { display: "block", marginBottom: 4, fontSize: 13, fontWeight: 600 },
  input: {
    width: "100%", padding: "10px 12px", border: "1px solid #ddd",
    borderRadius: 8, fontSize: 15, marginBottom: 16,
  },
  btn: {
    width: "100%", padding: "11px 0", background: "#4f46e5", color: "#fff",
    border: "none", borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: "pointer",
  },
  btnSecondary: {
    background: "none", border: "none", color: "#4f46e5",
    fontSize: 13, cursor: "pointer", padding: 0, textDecoration: "underline",
  },
  error:   { color: "#dc2626", marginBottom: 12, fontSize: 13 },
  success: {
    color: "#16a34a", background: "#f0fdf4", border: "1px solid #86efac",
    borderRadius: 8, padding: "12px 16px", marginBottom: 16, fontSize: 14,
  },
  link:         { textAlign: "center", marginTop: 16, fontSize: 13 },
  forgotWrap:   { textAlign: "right", marginTop: -8, marginBottom: 16 },
};

export default function Login() {
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  const [showForgot, setShowForgot]         = useState(false);
  const [forgotEmail, setForgotEmail]       = useState("");
  const [forgotSent, setForgotSent]         = useState(false);
  const [forgotLoading, setForgotLoading]   = useState(false);
  const [forgotError, setForgotError]       = useState("");

  const { setUser } = useAuth();
  const navigate    = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post("/auth/login", { email, password });
      setUser(res.data.user);
      navigate("/");
    } catch (err) {
      setError(err.response?.data?.error || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async (e) => {
    e.preventDefault();
    setForgotError("");
    setForgotLoading(true);
    try {
      await api.post("/auth/forgot-password", { email: forgotEmail });
      setForgotSent(true);
    } catch (err) {
      setForgotError(err.response?.data?.error || "Request failed");
    } finally {
      setForgotLoading(false);
    }
  };

  if (showForgot) {
    return (
      <div style={styles.page}>
        <div style={styles.card}>
          <h1 style={styles.title}>Reset Password</h1>
          {forgotSent ? (
            <>
              <p style={styles.success}>
                If that email exists, a reset link has been sent. Check your inbox.
              </p>
              <p style={styles.link}>
                <button style={styles.btnSecondary} onClick={() => {
                  setShowForgot(false);
                  setForgotSent(false);
                  setForgotEmail("");
                }}>
                  Back to login
                </button>
              </p>
            </>
          ) : (
            <form onSubmit={handleForgot}>
              {forgotError && <p style={styles.error}>{forgotError}</p>}
              <label style={styles.label}>Email</label>
              <input
                style={styles.input}
                type="email"
                value={forgotEmail}
                onChange={e => setForgotEmail(e.target.value)}
                required
                autoFocus
              />
              <button style={styles.btn} type="submit" disabled={forgotLoading}>
                {forgotLoading ? "Sending…" : "Send reset link"}
              </button>
              <p style={styles.link}>
                <button style={styles.btnSecondary} type="button"
                  onClick={() => { setShowForgot(false); setForgotError(""); }}>
                  Back to login
                </button>
              </p>
            </form>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>CloudDrive</h1>
        <form onSubmit={handleSubmit}>
          {error && <p style={styles.error}>{error}</p>}
          <label style={styles.label}>Email</label>
          <input
            style={styles.input}
            type="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            required
            autoFocus
          />
          <label style={styles.label}>Password</label>
          <input
            style={styles.input}
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
          />
          <div style={styles.forgotWrap}>
            <button type="button" style={styles.btnSecondary}
              onClick={() => { setShowForgot(true); setError(""); }}>
              Forgot password?
            </button>
          </div>
          <button style={styles.btn} type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
        <p style={styles.link}>
          Don't have an account? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  );
}
