import React, { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./App";

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
  error:   { color: "#dc2626", marginBottom: 12, fontSize: 13 },
  success: {
    color: "#16a34a", background: "#f0fdf4", border: "1px solid #86efac",
    borderRadius: 8, padding: "12px 16px", marginBottom: 16, fontSize: 14,
  },
  link: { textAlign: "center", marginTop: 16, fontSize: 13 },
};

export default function ResetPassword() {
  const token = new URLSearchParams(window.location.search).get("token") || "";

  const [password, setPassword]   = useState("");
  const [confirm, setConfirm]     = useState("");
  const [error, setError]         = useState("");
  const [loading, setLoading]     = useState(false);
  const [success, setSuccess]     = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) { setError("Passwords do not match"); return; }
    if (password.length < 8)  { setError("Password must be at least 8 characters"); return; }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: password });
      setSuccess(true);
    } catch (err) {
      setError(err.response?.data?.error || "Reset failed");
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div style={styles.page}>
        <div style={styles.card}>
          <h1 style={styles.title}>Reset Password</h1>
          <p style={styles.error}>Invalid or missing reset token.</p>
          <p style={styles.link}><Link to="/login">Back to login</Link></p>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div style={styles.page}>
        <div style={styles.card}>
          <h1 style={styles.title}>Reset Password</h1>
          <p style={styles.success}>Password reset successfully!</p>
          <p style={styles.link}><Link to="/login">Back to login</Link></p>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={styles.title}>Reset Password</h1>
        <form onSubmit={handleSubmit}>
          {error && <p style={styles.error}>{error}</p>}
          <label style={styles.label}>New Password</label>
          <input
            style={styles.input}
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            required
            autoFocus
          />
          <label style={styles.label}>Confirm Password</label>
          <input
            style={styles.input}
            type="password"
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            required
          />
          <button style={styles.btn} type="submit" disabled={loading}>
            {loading ? "Resetting…" : "Reset Password"}
          </button>
        </form>
        <p style={styles.link}><Link to="/login">Back to login</Link></p>
      </div>
    </div>
  );
}
