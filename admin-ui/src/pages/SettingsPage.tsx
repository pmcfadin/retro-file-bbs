import { useEffect, useState } from "react";
import { api } from "../api";

export default function SettingsPage() {
  const [scanlines, setScanlines] = useState(() => localStorage.getItem("crt-scanlines") !== "off");
  const [fileCount, setFileCount] = useState(0);
  const [categoryCount, setCategoryCount] = useState(0);
  useEffect(() => {
    api.getIndexerStatus().then((s) => {
      setFileCount(s.file_count);
      setCategoryCount(s.category_count);
    });
  }, []);

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

  return (
    <>
      <h1 className="page-title">SETTINGS</h1>

      <h3 style={{ color: "var(--amber)", marginBottom: 12 }}>Server Info</h3>
      <dl className="info-grid">
        <dt>Version</dt>
        <dd>CP/M Software Depot v1.0</dd>
        <dt>Telnet Port</dt>
        <dd>2323</dd>
        <dt>Web Port</dt>
        <dd>8080</dd>
        <dt>Files</dt>
        <dd>{fileCount}</dd>
        <dt>Categories</dt>
        <dd>{categoryCount}</dd>
      </dl>

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
