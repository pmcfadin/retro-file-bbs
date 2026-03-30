import { useEffect, useState } from "react";
import { api } from "../api";
import type { ServerConfig } from "../api";

export default function SettingsPage() {
  const [scanlines, setScanlines] = useState(() => localStorage.getItem("crt-scanlines") !== "off");
  const [fileCount, setFileCount] = useState(0);
  const [categoryCount, setCategoryCount] = useState(0);
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [editVersion, setEditVersion] = useState("");
  const [editTelnetPort, setEditTelnetPort] = useState("");
  const [editWebPort, setEditWebPort] = useState("");
  const [editCpmRoot, setEditCpmRoot] = useState("");
  const [editDbPath, setEditDbPath] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  useEffect(() => {
    api.getConfig().then((c) => {
      setConfig(c);
      setEditVersion(c.version);
      setEditTelnetPort(String(c.telnet_port));
      setEditWebPort(String(c.web_port));
      setEditCpmRoot(c.cpm_root);
      setEditDbPath(c.db_path);
    });
    api.getIndexerStatus().then((s) => {
      setFileCount(s.file_count);
      setCategoryCount(s.category_count);
    });
  }, []);

  const startEditing = () => {
    setEditing(true);
    setSaveMsg("");
  };

  const cancelEditing = () => {
    if (config) {
      setEditVersion(config.version);
      setEditTelnetPort(String(config.telnet_port));
      setEditWebPort(String(config.web_port));
      setEditCpmRoot(config.cpm_root);
      setEditDbPath(config.db_path);
    }
    setEditing(false);
    setSaveMsg("");
  };

  const saveConfig = async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      const patch: Record<string, unknown> = {};
      if (editVersion !== config?.version) patch.version = editVersion;
      const tp = parseInt(editTelnetPort, 10);
      if (!isNaN(tp) && tp !== config?.telnet_port) patch.telnet_port = tp;
      const wp = parseInt(editWebPort, 10);
      if (!isNaN(wp) && wp !== config?.web_port) patch.web_port = wp;
      if (editCpmRoot !== config?.cpm_root) patch.cpm_root = editCpmRoot;
      if (editDbPath !== config?.db_path) patch.db_path = editDbPath;

      if (Object.keys(patch).length === 0) {
        setEditing(false);
        return;
      }

      await api.patchConfig(patch as Parameters<typeof api.patchConfig>[0]);
      const updated = await api.getConfig();
      setConfig(updated);
      setEditVersion(updated.version);
      setEditTelnetPort(String(updated.telnet_port));
      setEditWebPort(String(updated.web_port));
      setEditCpmRoot(updated.cpm_root);
      setEditDbPath(updated.db_path);
      setEditing(false);
      setSaveMsg("Saved. Port changes take effect on restart.");
    } catch (e) {
      setSaveMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const toggleScanlines = () => {
    const next = !scanlines;
    setScanlines(next);
    if (next) {
      document.body.classList.add("crt-scanlines");
      localStorage.setItem("crt-scanlines", "on");
    } else {
      document.body.classList.remove("crt-scanlines");
      localStorage.setItem("crt-scanlines", "off");
    }
  };

  const inputStyle = {
    background: "var(--bg, #111)",
    border: "1px solid var(--amber, #ffb000)",
    color: "var(--green, #33ff33)",
    fontFamily: "inherit",
    fontSize: "inherit",
    padding: "2px 6px",
    width: "220px",
  };

  const wideInputStyle = { ...inputStyle, width: "400px" };

  return (
    <>
      <h1 className="page-title">SETTINGS</h1>

      <h3 style={{ color: "var(--amber)", marginBottom: 12 }}>
        Server Info
        {!editing && (
          <button className="term-btn" onClick={startEditing} style={{ marginLeft: 16, fontSize: 12 }}>
            [ EDIT ]
          </button>
        )}
      </h3>
      <dl className="info-grid">
        <dt>Version</dt>
        <dd>
          {editing ? (
            <input style={inputStyle} value={editVersion} onChange={(e) => setEditVersion(e.target.value)} />
          ) : (
            config?.version ?? "…"
          )}
        </dd>
        <dt>Telnet Port</dt>
        <dd>
          {editing ? (
            <input style={inputStyle} type="number" value={editTelnetPort} onChange={(e) => setEditTelnetPort(e.target.value)} />
          ) : (
            config?.telnet_port ?? "…"
          )}
        </dd>
        <dt>Web Port</dt>
        <dd>
          {editing ? (
            <input style={inputStyle} type="number" value={editWebPort} onChange={(e) => setEditWebPort(e.target.value)} />
          ) : (
            config?.web_port ?? "…"
          )}
        </dd>
        <dt>File Archive</dt>
        <dd>
          {editing ? (
            <input style={wideInputStyle} value={editCpmRoot} onChange={(e) => setEditCpmRoot(e.target.value)} />
          ) : (
            config?.cpm_root ?? "…"
          )}
        </dd>
        <dt>Database</dt>
        <dd>
          {editing ? (
            <input style={wideInputStyle} value={editDbPath} onChange={(e) => setEditDbPath(e.target.value)} />
          ) : (
            config?.db_path ?? "…"
          )}
        </dd>
        <dt>Files</dt>
        <dd>{fileCount}</dd>
        <dt>Categories</dt>
        <dd>{categoryCount}</dd>
      </dl>

      {editing && (
        <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center" }}>
          <button className="term-btn" onClick={saveConfig} disabled={saving}>
            {saving ? "[ SAVING... ]" : "[ SAVE ]"}
          </button>
          <button className="term-btn" onClick={cancelEditing} disabled={saving}>
            [ CANCEL ]
          </button>
        </div>
      )}

      {saveMsg && (
        <div style={{ marginTop: 8, color: saveMsg.startsWith("Error") ? "#ff4444" : "var(--amber)", fontSize: 12 }}>
          {saveMsg}
        </div>
      )}

      <h3 style={{ color: "var(--amber)", margin: "24px 0 12px" }}>Display</h3>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button className="term-btn" onClick={toggleScanlines}>
          {scanlines ? "[ SCANLINES: ON ]" : "[ SCANLINES: OFF ]"}
        </button>
        <span style={{ color: "var(--dim-green)", fontSize: 12 }}>
          Toggle CRT scanline overlay effect
        </span>
      </div>
    </>
  );
}
