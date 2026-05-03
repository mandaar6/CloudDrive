import React, { useState, useEffect, useRef, useCallback } from "react";
import { api, useAuth } from "./App";
import ShareModal from "./ShareModal";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(b) {
  if (!b || b === 0) return "0 B";
  const k = 1024, sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(b) / Math.log(k));
  return `${(b / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString();
}

const EXT_COLORS = {
  pdf:  { bg: "#fef2f2", color: "#dc2626" },
  txt:  { bg: "#f0fdf4", color: "#16a34a" },
  doc:  { bg: "#eff6ff", color: "#2563eb" },
  docx: { bg: "#eff6ff", color: "#2563eb" },
  png:  { bg: "#fdf4ff", color: "#9333ea" },
  jpg:  { bg: "#fdf4ff", color: "#9333ea" },
  jpeg: { bg: "#fdf4ff", color: "#9333ea" },
  gif:  { bg: "#fdf4ff", color: "#9333ea" },
};

function fileExt(filename) {
  return filename?.includes(".") ? filename.split(".").pop().toLowerCase() : "";
}

function TypeBadge({ filename }) {
  const ext = fileExt(filename);
  const c   = EXT_COLORS[ext] || { bg: "#f3f4f6", color: "#6b7280" };
  return (
    <span style={{
      display: "inline-block", padding: "2px 7px", borderRadius: 4,
      background: c.bg, color: c.color, fontSize: 11, fontWeight: 700,
      letterSpacing: 0.3, textTransform: "uppercase",
    }}>
      {ext || "FILE"}
    </span>
  );
}

function PermBadge({ perm }) {
  return (
    <span style={{
      background: perm === "edit" ? "#dbeafe" : "#f0fdf4",
      color:      perm === "edit" ? "#1d4ed8" : "#15803d",
      padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 600,
    }}>
      {perm}
    </span>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const S = {
  page:    { display: "flex", flexDirection: "column", minHeight: "100vh", background: "#f5f7fa" },
  nav: {
    background: "#fff", padding: "0 2rem", height: 56, flexShrink: 0,
    display: "flex", alignItems: "center", justifyContent: "space-between",
    boxShadow: "0 1px 0 #e5e7eb", position: "sticky", top: 0, zIndex: 10,
  },
  navTitle:  { fontWeight: 700, fontSize: 18, color: "#4f46e5" },
  navRight:  { display: "flex", alignItems: "center", gap: 16, fontSize: 14 },
  layout:    { display: "flex", flex: 1, overflow: "hidden", minHeight: 0 },
  sidebar: {
    width: 200, background: "#fff", borderRight: "1px solid #e5e7eb",
    padding: "1.25rem 0", flexShrink: 0, overflowY: "auto",
  },
  sideSection: { padding: "4px 16px 8px", fontSize: 11, fontWeight: 600,
                  color: "#9ca3af", textTransform: "uppercase", letterSpacing: 0.5 },
  navItem: (active) => ({
    display: "block", width: "100%", padding: "9px 20px", textAlign: "left",
    background: active ? "#ede9fe" : "transparent",
    color:      active ? "#4f46e5" : "#374151",
    border: "none", borderLeft: `3px solid ${active ? "#4f46e5" : "transparent"}`,
    cursor: "pointer", fontSize: 14, fontWeight: active ? 600 : 400,
    boxSizing: "border-box",
  }),
  main:    { flex: 1, padding: "2rem", overflowY: "auto" },
  detail: {
    width: 288, background: "#fff", borderLeft: "1px solid #e5e7eb",
    padding: "1.5rem", flexShrink: 0, overflowY: "auto",
  },

  // Sections
  sectionHeader: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    marginBottom: 16,
  },
  h2: { fontSize: 16, fontWeight: 700, margin: 0 },
  card: {
    background: "#fff", borderRadius: 12, padding: "1.5rem", marginBottom: 24,
    boxShadow: "0 2px 8px rgba(0,0,0,.06)",
  },
  uploadZone: {
    border: "2px dashed #c7d2fe", borderRadius: 10, padding: "1.5rem",
    textAlign: "center", cursor: "pointer", color: "#6b7280", fontSize: 14,
  },

  // Toggle
  toggleGroup: { display: "flex", gap: 4, background: "#f3f4f6", borderRadius: 8, padding: 3 },
  toggleBtn: (active) => ({
    padding: "4px 14px", border: "none", borderRadius: 6, cursor: "pointer",
    fontSize: 13, fontWeight: 600,
    background: active ? "#fff" : "transparent",
    color:      active ? "#4f46e5" : "#6b7280",
    boxShadow:  active ? "0 1px 3px rgba(0,0,0,.1)" : "none",
  }),

  // Table
  table:  { width: "100%", borderCollapse: "collapse", fontSize: 14 },
  th: {
    textAlign: "left", padding: "8px 10px", borderBottom: "2px solid #f0f0f0",
    fontWeight: 600, fontSize: 12, color: "#6b7280", textTransform: "uppercase",
  },
  td:     { padding: "10px", borderBottom: "1px solid #f9f9f9", verticalAlign: "middle" },

  // Grid
  grid: {
    display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(155px, 1fr))", gap: 14,
  },
  fileCard: (selected) => ({
    background: "#fff", borderRadius: 10, padding: "1rem",
    border: `2px solid ${selected ? "#4f46e5" : "transparent"}`,
    boxShadow: selected ? "0 0 0 1px #c7d2fe" : "0 2px 6px rgba(0,0,0,.06)",
    cursor: "pointer", position: "relative",
  }),

  // Buttons
  btn: (v) => ({
    padding: "4px 12px", borderRadius: 6, border: "none", fontSize: 12,
    fontWeight: 600, cursor: "pointer", marginRight: 4,
    background: v === "primary" ? "#4f46e5"
              : v === "danger"  ? "#fee2e2"
              : v === "ghost"   ? "transparent"
              : "#f3f4f6",
    color:      v === "primary" ? "#fff"
              : v === "danger"  ? "#dc2626"
              : v === "ghost"   ? "#4f46e5"
              : "#374151",
    textDecoration: v === "ghost" ? "underline" : "none",
  }),
  logoutBtn: {
    padding: "6px 14px", background: "transparent", border: "1px solid #e5e7eb",
    borderRadius: 8, cursor: "pointer", fontSize: 13,
  },
  sharedBtn: {
    display: "inline-block", marginLeft: 6, padding: "1px 7px", borderRadius: 10,
    background: "#e0e7ff", color: "#4338ca", fontSize: 11, fontWeight: 600,
    border: "none", cursor: "pointer", verticalAlign: "middle",
  },
  starBtn: (starred) => ({
    background: "transparent", border: "none", cursor: "pointer",
    fontSize: 16, color: starred ? "#f59e0b" : "#d1d5db", padding: 0,
  }),

  // Tabs
  tabs:    { display: "flex", gap: 0, borderBottom: "2px solid #e5e7eb", marginBottom: 20 },
  tab: (active) => ({
    padding: "9px 20px", border: "none", background: "transparent",
    borderBottom: `2px solid ${active ? "#4f46e5" : "transparent"}`,
    color:   active ? "#4f46e5" : "#6b7280",
    fontWeight: active ? 700 : 400, fontSize: 14, cursor: "pointer", marginBottom: -2,
  }),

  // Preview modal
  overlay: {
    position: "fixed", inset: 0, background: "rgba(0,0,0,.6)",
    display: "flex", alignItems: "center", justifyContent: "center", zIndex: 300,
  },
  previewModal: {
    background: "#fff", borderRadius: 12, display: "flex", flexDirection: "column",
    width: "92vw", maxWidth: 960, height: "88vh",
    boxShadow: "0 16px 48px rgba(0,0,0,.24)", overflow: "hidden",
  },
  previewHeader: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "1rem 1.5rem", borderBottom: "1px solid #e5e7eb", flexShrink: 0,
  },
  previewBody: { flex: 1, overflow: "auto", display: "flex", alignItems: "center",
                  justifyContent: "center", padding: "1rem", background: "#f9fafb" },

  // Error
  errorBar: {
    background: "#fee2e2", color: "#dc2626", padding: "10px 16px",
    borderRadius: 8, marginBottom: 16, fontSize: 13,
  },
};

// ── Preview Modal ─────────────────────────────────────────────────────────────

function PreviewModal({ file, data, onClose, onDownload }) {
  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.previewModal} onClick={e => e.stopPropagation()}>
        <div style={S.previewHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <TypeBadge filename={file.filename} />
            <span style={{ fontWeight: 600, fontSize: 15 }}>{file.filename}</span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button style={S.btn("primary")} onClick={onDownload}>Download</button>
            <button style={S.btn()} onClick={onClose}>Close</button>
          </div>
        </div>
        <div style={S.previewBody}>
          {data.type === "image" && (
            <img
              src={data.url}
              alt={file.filename}
              style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain", borderRadius: 6 }}
            />
          )}
          {data.type === "text" && (
            <pre style={{
              width: "100%", height: "100%", margin: 0, padding: "1rem",
              fontSize: 13, fontFamily: "monospace", background: "#fff",
              borderRadius: 8, overflow: "auto", whiteSpace: "pre-wrap",
              wordBreak: "break-word", alignSelf: "stretch",
            }}>
              {data.content}
            </pre>
          )}
          {data.type === "pdf" && (
            <iframe
              src={data.url}
              title="PDF Preview"
              style={{ width: "100%", height: "100%", border: "none", borderRadius: 6 }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ── Detail Panel ──────────────────────────────────────────────────────────────

function DetailPanel({ file, shares, isOwner, onClose, onDownload, onDelete, onShare, onStar, onRevokeShare }) {
  return (
    <div style={S.detail}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <span style={{ fontWeight: 700, fontSize: 15, wordBreak: "break-all" }}>{file.filename}</span>
        <button style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#9ca3af", marginLeft: 8 }} onClick={onClose}>×</button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 13, color: "#374151", marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#9ca3af" }}>Type</span>
          <TypeBadge filename={file.filename} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#9ca3af" }}>Size</span>
          <span>{formatBytes(file.size_bytes)}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#9ca3af" }}>Uploaded</span>
          <span>{fmtDate(file.uploaded_at)}</span>
        </div>
        {!isOwner && (
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ color: "#9ca3af" }}>Access</span>
            <span style={{ color: "#6b7280" }}>Shared with you</span>
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
        <button style={{ ...S.btn("primary"), width: "100%", padding: "8px 0", marginRight: 0 }} onClick={onDownload}>
          Download
        </button>
        {isOwner && (
          <>
            <button
              style={{ ...S.btn(), width: "100%", padding: "8px 0", marginRight: 0 }}
              onClick={onStar}
            >
              {file.is_starred ? "Unstar" : "Star"}
            </button>
            <button style={{ ...S.btn(), width: "100%", padding: "8px 0", marginRight: 0 }} onClick={onShare}>
              Share
            </button>
            <button style={{ ...S.btn("danger"), width: "100%", padding: "8px 0", marginRight: 0 }} onClick={onDelete}>
              Move to Trash
            </button>
          </>
        )}
      </div>

      {isOwner && (
        <div>
          <p style={{ fontSize: 12, fontWeight: 700, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 10 }}>
            Shared with
          </p>
          {shares.length === 0 ? (
            <p style={{ fontSize: 13, color: "#9ca3af" }}>Not shared with anyone.</p>
          ) : (
            shares.map(s => (
              <div key={s.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #f3f4f6", fontSize: 13 }}>
                <div>
                  <div style={{ fontWeight: 500 }}>{s.shared_with_email}</div>
                  <PermBadge perm={s.permission} />
                </div>
                <button
                  style={{ background: "none", border: "1px solid #e5e7eb", color: "#dc2626", borderRadius: 6, padding: "3px 8px", fontSize: 11, cursor: "pointer" }}
                  onClick={() => onRevokeShare(s.id)}
                >
                  Revoke
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard({ activeSection, setActiveSection }) {
  const { user, logout } = useAuth();

  const [owned,       setOwned]       = useState([]);
  const [sharedFiles, setSharedFiles] = useState([]);
  const [trashFiles,  setTrashFiles]  = useState([]);
  const [starredFiles, setStarredFiles] = useState([]);
  const [outgoing,    setOutgoing]    = useState([]);
  const [incoming,    setIncoming]    = useState([]);

  const [viewMode,     setViewMode]     = useState("list");
  const [selectedFile, setSelectedFile] = useState(null);
  const [detailShares, setDetailShares] = useState([]);
  const [previewModal, setPreviewModal] = useState(null); // { file, data }
  const [shareTarget,  setShareTarget]  = useState(null);
  const [sharedTab,    setSharedTab]    = useState("outgoing");
  const [uploading,       setUploading]       = useState(false);
  const [uploadProgress,  setUploadProgress]  = useState(0);
  const [error,           setError]           = useState("");

  const fileInput = useRef();

  // ── Fetch functions ──────────────────────────────────────────────────────────

  const fetchFiles = useCallback(() => {
    api.get("/files/")
      .then(res => { setOwned(res.data.owned || []); setSharedFiles(res.data.shared || []); })
      .catch(() => setError("Failed to load files"));
  }, []);

  const fetchStarred = useCallback(() => {
    api.get("/files/?starred=true")
      .then(res => setStarredFiles(res.data.owned || []))
      .catch(() => setError("Failed to load starred files"));
  }, []);

  const fetchTrash = useCallback(() => {
    api.get("/files/trash")
      .then(res => setTrashFiles(res.data.trash || []))
      .catch(() => setError("Failed to load trash"));
  }, []);

  const fetchShared = useCallback(() => {
    Promise.all([api.get("/shares/outgoing"), api.get("/shares/incoming")])
      .then(([out, inc]) => {
        setOutgoing(out.data.outgoing || []);
        setIncoming(inc.data.incoming || []);
      })
      .catch(() => setError("Failed to load shares"));
  }, []);

  // ── Effects ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    setSelectedFile(null);
    setError("");
    if      (activeSection === "all-files") fetchFiles();
    else if (activeSection === "starred")   fetchStarred();
    else if (activeSection === "trash")     fetchTrash();
    else if (activeSection === "shared")    fetchShared();
  }, [activeSection, fetchFiles, fetchStarred, fetchTrash, fetchShared]);

  // Fetch detail panel shares whenever selected file changes
  useEffect(() => {
    if (!selectedFile || selectedFile.owner_id !== user?.id) {
      setDetailShares([]);
      return;
    }
    api.get(`/files/${selectedFile.id}/shares`)
      .then(res => setDetailShares(res.data.shares || []))
      .catch(() => setDetailShares([]));
  }, [selectedFile?.id, user?.id]);

  // ── Handlers ─────────────────────────────────────────────────────────────────

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadProgress(0);
    setError("");

    try {
      // Step 1: get presigned POST credentials from backend
      const params = new URLSearchParams({
        filename:     file.name,
        content_type: file.type || "application/octet-stream",
      });
      const urlRes = await api.get(`/files/upload-url?${params}`);
      const { upload_url, fields, s3_key } = urlRes.data;

      // Step 2: POST file directly to S3 using XHR for progress tracking
      const formData = new FormData();
      for (const [key, val] of Object.entries(fields)) {
        formData.append(key, val);
      }
      formData.append("file", file); // file must be last per S3 spec

      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.upload.addEventListener("progress", (ev) => {
          if (ev.lengthComputable) {
            setUploadProgress(Math.round((ev.loaded / ev.total) * 100));
          }
        });
        xhr.addEventListener("load", () => {
          if (xhr.status === 204 || xhr.status === 200) resolve();
          else reject(new Error(`S3 upload failed (HTTP ${xhr.status})`));
        });
        xhr.addEventListener("error", () => reject(new Error("Network error during upload")));
        xhr.open("POST", upload_url);
        // Do NOT set Content-Type — browser sets it with multipart boundary
        xhr.send(formData);
      });

      // Step 3: register the uploaded file in the backend
      await api.post("/files/confirm-upload", {
        filename:     file.name,
        s3_key,
        size_bytes:   file.size,
        content_type: file.type || "application/octet-stream",
      });

      // Step 4: refresh file list
      fetchFiles();
    } catch (err) {
      setError(err.response?.data?.error || err.message || "Upload failed");
    } finally {
      setUploading(false);
      setUploadProgress(0);
      fileInput.current.value = "";
    }
  };

  const handleDownload = async (file) => {
    try {
      const res = await api.get(`/files/${file.id}/download`);
      window.open(res.data.download_url, "_blank", "noopener");
    } catch {
      setError("Download failed");
    }
  };

  const handleDelete = async (file) => {
    if (!window.confirm(`Move "${file.filename}" to trash?`)) return;
    try {
      await api.delete(`/files/${file.id}`);
      setSelectedFile(null);
      fetchFiles();
    } catch {
      setError("Delete failed");
    }
  };

  const handleStar = async (file) => {
    try {
      const res = await api.put(`/files/${file.id}/star`);
      const newVal = res.data.is_starred;
      const update = arr => arr.map(f => f.id === file.id ? { ...f, is_starred: newVal } : f);
      setOwned(update);
      setStarredFiles(update);
      if (selectedFile?.id === file.id) setSelectedFile(prev => ({ ...prev, is_starred: newVal }));
    } catch {
      setError("Failed to update star");
    }
  };

  const handlePreview = async (e, file) => {
    e.stopPropagation();
    try {
      const res = await api.get(`/files/${file.id}/preview`);
      const data = res.data;
      if (data.type === "download") {
        window.open(data.url, "_blank", "noopener");
      } else {
        setPreviewModal({ file, data });
      }
    } catch {
      setError("Preview failed");
    }
  };

  const handleRestore = async (file) => {
    try {
      await api.post(`/files/${file.id}/restore`);
      fetchTrash();
    } catch {
      setError("Restore failed");
    }
  };

  const handlePermanentDelete = async (file) => {
    if (!window.confirm(`Permanently delete "${file.filename}"? This cannot be undone.`)) return;
    try {
      await api.delete(`/files/${file.id}/permanent`);
      fetchTrash();
    } catch {
      setError("Permanent delete failed");
    }
  };

  const handleRevokeShare = async (shareId) => {
    try {
      await api.delete(`/shares/${shareId}`);
      // Refresh detail shares in panel
      if (selectedFile) {
        api.get(`/files/${selectedFile.id}/shares`)
          .then(res => setDetailShares(res.data.shares || []))
          .catch(() => {});
      }
      // Also refresh outgoing if in shared section
      if (activeSection === "shared") fetchShared();
    } catch {
      setError("Failed to revoke share");
    }
  };

  const handleSelectFile = (file) => {
    setSelectedFile(prev => prev?.id === file.id ? null : file);
  };

  // ── File list renderers ───────────────────────────────────────────────────────

  const renderListView = (files, opts = {}) => (
    <table style={S.table}>
      <thead>
        <tr>
          <th style={S.th}>Name</th>
          <th style={S.th}>Size</th>
          <th style={S.th}>Type</th>
          <th style={S.th}>Date</th>
          <th style={S.th}>Actions</th>
        </tr>
      </thead>
      <tbody>
        {files.length === 0 ? (
          <tr>
            <td colSpan={5} style={{ ...S.td, color: "#9ca3af", textAlign: "center", padding: 24 }}>
              No files
            </td>
          </tr>
        ) : files.map(f => (
          <tr
            key={f.id}
            style={{ background: selectedFile?.id === f.id ? "#f5f3ff" : "transparent", cursor: "pointer" }}
            onClick={() => handleSelectFile(f)}
          >
            <td style={S.td}>
              <button
                style={S.btn("ghost")}
                onClick={(e) => handlePreview(e, f)}
              >
                {f.filename}
              </button>
              {f.is_starred && <span style={{ marginLeft: 4, color: "#f59e0b" }}>★</span>}
              {f.is_shared && (
                <button
                  style={S.sharedBtn}
                  onClick={(e) => { e.stopPropagation(); setShareTarget(f); }}
                >
                  Shared
                </button>
              )}
            </td>
            <td style={S.td}>{formatBytes(f.size_bytes)}</td>
            <td style={S.td}><TypeBadge filename={f.filename} /></td>
            <td style={S.td}>{fmtDate(f.uploaded_at)}</td>
            <td style={S.td}>
              <button style={S.btn("primary")} onClick={(e) => { e.stopPropagation(); handleDownload(f); }}>
                Download
              </button>
              {opts.showOwnerActions && f.owner_id === user?.id && (
                <>
                  <button style={S.btn()} onClick={(e) => { e.stopPropagation(); setShareTarget(f); }}>Share</button>
                  <button style={S.btn("danger")} onClick={(e) => { e.stopPropagation(); handleDelete(f); }}>Delete</button>
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderGridView = (files, opts = {}) => (
    <div style={S.grid}>
      {files.length === 0 && (
        <p style={{ color: "#9ca3af", fontSize: 14, gridColumn: "1/-1" }}>No files</p>
      )}
      {files.map(f => (
        <div
          key={f.id}
          style={S.fileCard(selectedFile?.id === f.id)}
          onClick={() => handleSelectFile(f)}
        >
          <div style={{ marginBottom: 8 }}>
            <TypeBadge filename={f.filename} />
            {f.is_starred && <span style={{ marginLeft: 6, color: "#f59e0b", fontSize: 14 }}>★</span>}
          </div>
          <button
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "#4f46e5", fontWeight: 600, fontSize: 13,
              textAlign: "left", padding: 0, wordBreak: "break-all", marginBottom: 6,
              textDecoration: "underline",
            }}
            onClick={(e) => handlePreview(e, f)}
          >
            {f.filename}
          </button>
          <div style={{ fontSize: 11, color: "#9ca3af" }}>{formatBytes(f.size_bytes)}</div>
          {f.is_shared && (
            <button
              style={{ ...S.sharedBtn, marginLeft: 0, marginTop: 6, display: "block" }}
              onClick={(e) => { e.stopPropagation(); setShareTarget(f); }}
            >
              Shared
            </button>
          )}
          {opts.showOwnerActions && f.owner_id === user?.id && (
            <div style={{ marginTop: 8, display: "flex", gap: 4, flexWrap: "wrap" }}>
              <button style={{ ...S.btn("danger"), padding: "3px 8px" }}
                onClick={(e) => { e.stopPropagation(); handleDelete(f); }}>
                Delete
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );

  const renderFiles = (files, opts = {}) =>
    viewMode === "grid" ? renderGridView(files, opts) : renderListView(files, opts);

  const ViewToggle = () => (
    <div style={S.toggleGroup}>
      <button style={S.toggleBtn(viewMode === "list")} onClick={() => setViewMode("list")}>List</button>
      <button style={S.toggleBtn(viewMode === "grid")} onClick={() => setViewMode("grid")}>Grid</button>
    </div>
  );

  // ── Section renders ───────────────────────────────────────────────────────────

  const renderAllFiles = () => (
    <>
      {/* Upload */}
      <div style={S.card}>
        <p style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>Upload File</p>
        <div
          style={{ ...S.uploadZone, cursor: uploading ? "default" : "pointer" }}
          onClick={!uploading ? () => fileInput.current.click() : undefined}
        >
          {uploading ? (
            <div>
              <p style={{ margin: "0 0 10px", fontWeight: 600 }}>Uploading… {uploadProgress}%</p>
              <div style={{ background: "#e0e7ff", borderRadius: 4, height: 6, overflow: "hidden" }}>
                <div style={{
                  background: "#4f46e5", height: "100%",
                  width: `${uploadProgress}%`, transition: "width 0.15s ease",
                }} />
              </div>
            </div>
          ) : (
            "Click to select a file — pdf, txt, doc, docx, png, jpg, jpeg, gif, mp4, mov, zip, csv, xlsx, pptx (up to 5 GB, uploaded directly to S3)"
          )}
        </div>
        <input ref={fileInput} type="file" style={{ display: "none" }} onChange={handleUpload} />
      </div>

      {/* My Files */}
      <div style={S.card}>
        <div style={S.sectionHeader}>
          <h2 style={S.h2}>My Files</h2>
          <ViewToggle />
        </div>
        {renderFiles(owned, { showOwnerActions: true })}
      </div>

      {/* Shared with me */}
      {sharedFiles.length > 0 && (
        <div style={S.card}>
          <div style={S.sectionHeader}>
            <h2 style={S.h2}>Shared with Me</h2>
          </div>
          {renderFiles(sharedFiles)}
        </div>
      )}
    </>
  );

  const renderStarred = () => (
    <div style={S.card}>
      <div style={S.sectionHeader}>
        <h2 style={S.h2}>Starred Files</h2>
        <ViewToggle />
      </div>
      {renderFiles(starredFiles, { showOwnerActions: true })}
    </div>
  );

  const renderTrash = () => (
    <div style={S.card}>
      <h2 style={{ ...S.h2, marginBottom: 16 }}>Trash</h2>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>Name</th>
            <th style={S.th}>Size</th>
            <th style={S.th}>Deleted</th>
            <th style={S.th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {trashFiles.length === 0 ? (
            <tr>
              <td colSpan={4} style={{ ...S.td, color: "#9ca3af", textAlign: "center", padding: 24 }}>
                Trash is empty
              </td>
            </tr>
          ) : trashFiles.map(f => (
            <tr key={f.id}>
              <td style={S.td}>
                <span style={{ fontWeight: 500 }}>{f.filename}</span>
              </td>
              <td style={S.td}>{formatBytes(f.size_bytes)}</td>
              <td style={S.td}>{fmtDate(f.deleted_at)}</td>
              <td style={S.td}>
                <button style={S.btn("primary")} onClick={() => handleRestore(f)}>Restore</button>
                <button style={S.btn("danger")} onClick={() => handlePermanentDelete(f)}>Delete Forever</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderShared = () => (
    <div style={S.card}>
      <h2 style={{ ...S.h2, marginBottom: 16 }}>Sharing</h2>
      <div style={S.tabs}>
        <button style={S.tab(sharedTab === "outgoing")} onClick={() => setSharedTab("outgoing")}>
          Shared by me ({outgoing.length})
        </button>
        <button style={S.tab(sharedTab === "incoming")} onClick={() => setSharedTab("incoming")}>
          Shared with me ({incoming.length})
        </button>
      </div>

      {sharedTab === "outgoing" && (
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>File</th>
              <th style={S.th}>Shared with</th>
              <th style={S.th}>Permission</th>
              <th style={S.th}>Date</th>
              <th style={S.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {outgoing.length === 0 ? (
              <tr><td colSpan={5} style={{ ...S.td, color: "#9ca3af", textAlign: "center", padding: 24 }}>No outgoing shares</td></tr>
            ) : outgoing.map(s => (
              <tr key={s.share_id}>
                <td style={S.td}>{s.filename}</td>
                <td style={S.td}>{s.shared_with_email}</td>
                <td style={S.td}><PermBadge perm={s.permission} /></td>
                <td style={S.td}>{fmtDate(s.created_at)}</td>
                <td style={S.td}>
                  <button
                    style={S.btn("danger")}
                    onClick={() => handleRevokeShare(s.share_id)}
                  >
                    Revoke
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {sharedTab === "incoming" && (
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>File</th>
              <th style={S.th}>Shared by</th>
              <th style={S.th}>Permission</th>
              <th style={S.th}>Date</th>
              <th style={S.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {incoming.length === 0 ? (
              <tr><td colSpan={5} style={{ ...S.td, color: "#9ca3af", textAlign: "center", padding: 24 }}>Nothing shared with you</td></tr>
            ) : incoming.map(s => (
              <tr key={s.share_id}>
                <td style={S.td}>{s.filename}</td>
                <td style={S.td}>{s.owner_username}</td>
                <td style={S.td}><PermBadge perm={s.permission} /></td>
                <td style={S.td}>{fmtDate(s.created_at)}</td>
                <td style={S.td}>
                  <button
                    style={S.btn("primary")}
                    onClick={() => handleDownload({ id: s.file_id })}
                  >
                    Download
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );

  const NAV_ITEMS = [
    { key: "all-files", label: "All Files" },
    { key: "starred",   label: "Starred"   },
    { key: "shared",    label: "Shared"    },
    { key: "trash",     label: "Trash"     },
  ];

  const isOwner = selectedFile && user && selectedFile.owner_id === user.id;

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div style={S.page}>
      {/* Top nav */}
      <nav style={S.nav}>
        <span style={S.navTitle}>CloudDrive</span>
        <div style={S.navRight}>
          <span style={{ color: "#6b7280" }}>{user?.email}</span>
          <button style={S.logoutBtn} onClick={logout}>Sign out</button>
        </div>
      </nav>

      <div style={S.layout}>
        {/* Sidebar */}
        <aside style={S.sidebar}>
          <p style={S.sideSection}>Navigation</p>
          {NAV_ITEMS.map(item => (
            <button
              key={item.key}
              style={S.navItem(activeSection === item.key)}
              onClick={() => setActiveSection(item.key)}
            >
              {item.label}
            </button>
          ))}
        </aside>

        {/* Main content */}
        <main style={S.main}>
          {error && (
            <div style={S.errorBar}>
              {error}
              <button style={{ float: "right", background: "none", border: "none", cursor: "pointer", color: "#dc2626" }} onClick={() => setError("")}>×</button>
            </div>
          )}
          {activeSection === "all-files" && renderAllFiles()}
          {activeSection === "starred"   && renderStarred()}
          {activeSection === "trash"     && renderTrash()}
          {activeSection === "shared"    && renderShared()}
        </main>

        {/* Detail panel */}
        {selectedFile && (
          <DetailPanel
            file={selectedFile}
            shares={detailShares}
            isOwner={isOwner}
            onClose={() => setSelectedFile(null)}
            onDownload={() => handleDownload(selectedFile)}
            onDelete={() => handleDelete(selectedFile)}
            onShare={() => setShareTarget(selectedFile)}
            onStar={() => handleStar(selectedFile)}
            onRevokeShare={handleRevokeShare}
          />
        )}
      </div>

      {/* Preview modal */}
      {previewModal && (
        <PreviewModal
          file={previewModal.file}
          data={previewModal.data}
          onClose={() => setPreviewModal(null)}
          onDownload={() => { handleDownload(previewModal.file); setPreviewModal(null); }}
        />
      )}

      {/* Share modal */}
      {shareTarget && (
        <ShareModal
          file={shareTarget}
          onClose={() => { setShareTarget(null); fetchFiles(); }}
        />
      )}
    </div>
  );
}
