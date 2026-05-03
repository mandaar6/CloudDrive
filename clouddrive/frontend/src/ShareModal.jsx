import React, { useState, useEffect } from "react";
import { api } from "./App";

const overlay = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,.45)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200,
};
const modal = {
  background: "#fff", borderRadius: 12, padding: "2rem",
  width: "100%", maxWidth: 500, boxShadow: "0 8px 32px rgba(0,0,0,.18)",
};
const rowStyle  = { display: "flex", gap: 8, marginBottom: 12 };
const inputStyle = {
  flex: 1, padding: "9px 12px", border: "1px solid #ddd",
  borderRadius: 8, fontSize: 14,
};
const selectStyle = {
  padding: "9px 12px", border: "1px solid #ddd",
  borderRadius: 8, fontSize: 14,
};
const btn = (variant) => ({
  padding: "9px 18px", borderRadius: 8, border: "none",
  fontSize: 14, fontWeight: 600, cursor: "pointer",
  background: variant === "primary" ? "#4f46e5"
            : variant === "danger"  ? "#fee2e2"
            : "#e5e7eb",
  color:      variant === "primary" ? "#fff"
            : variant === "danger"  ? "#dc2626"
            : "#374151",
});
const shareRow = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  padding: "8px 0", borderBottom: "1px solid #f0f0f0", fontSize: 13,
};
const permBadge = (perm) => ({
  background: perm === "edit" ? "#dbeafe" : "#f0fdf4",
  color:      perm === "edit" ? "#1d4ed8" : "#15803d",
  padding: "2px 10px", borderRadius: 99, fontSize: 12, fontWeight: 600,
});

export default function ShareModal({ file, onClose }) {
  const [email, setEmail]           = useState("");
  const [permission, setPermission] = useState("read");
  const [shares, setShares]         = useState([]);
  const [error, setError]           = useState("");
  const [success, setSuccess]       = useState("");

  const fetchShares = () => {
    api.get(`/files/${file.id}/shares`)
      .then(res => setShares(res.data.shares))
      .catch(() => {});
  };

  useEffect(fetchShares, [file.id]);

  const handleShare = async (e) => {
    e.preventDefault();
    setError(""); setSuccess("");
    try {
      await api.post(`/files/${file.id}/share`, { email, permission });
      setSuccess(`Shared with ${email}`);
      setEmail("");
      fetchShares();
    } catch (err) {
      setError(err.response?.data?.error || "Share failed");
    }
  };

  const handleRevoke = async (shareId) => {
    try {
      await api.delete(`/shares/${shareId}`);
      fetchShares();
    } catch (err) {
      setError(err.response?.data?.error || "Failed to revoke share");
    }
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={e => e.stopPropagation()}>
        <h2 style={{ marginBottom: 4, fontSize: 18 }}>Share "{file.filename}"</h2>
        <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 20 }}>
          Add a user by email to grant them access.
        </p>

        <form onSubmit={handleShare}>
          <div style={rowStyle}>
            <input
              style={inputStyle}
              type="email"
              placeholder="colleague@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
            <select
              style={selectStyle}
              value={permission}
              onChange={e => setPermission(e.target.value)}
            >
              <option value="read">Read</option>
              <option value="edit">Edit</option>
            </select>
            <button style={btn("primary")} type="submit">Share</button>
          </div>
          {error   && <p style={{ color: "#dc2626", fontSize: 13 }}>{error}</p>}
          {success && <p style={{ color: "#16a34a", fontSize: 13 }}>{success}</p>}
        </form>

        {shares.length > 0 && (
          <div style={{ marginTop: 20 }}>
            <p style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>Shared with</p>
            {shares.map(s => (
              <div key={s.id} style={shareRow}>
                <span style={{ flex: 1 }}>{s.shared_with_email}</span>
                <span style={permBadge(s.permission)}>{s.permission}</span>
                <button
                  style={{ ...btn("danger"), padding: "4px 10px", fontSize: 12, marginLeft: 8 }}
                  onClick={() => handleRevoke(s.id)}
                >
                  Revoke
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ textAlign: "right", marginTop: 24 }}>
          <button style={btn()} type="button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
