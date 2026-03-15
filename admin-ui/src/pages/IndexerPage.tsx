import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { IndexerStatusResponse } from "../api";
import { useToast } from "../useToast";

export default function IndexerPage() {
  const [status, setStatus] = useState<IndexerStatusResponse | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const { toast, showToast } = useToast();
  const logRef = useRef<HTMLDivElement>(null);

  const loadStatus = () => {
    api.getIndexerStatus().then(setStatus).catch(console.error);
  };

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket for indexer output
  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/api/indexer/output`);

    ws.onmessage = (e) => {
      setOutput((prev) => {
        const next = [...prev, e.data];
        if (next.length > 500) next.splice(0, next.length - 500);
        return next;
      });
    };

    return () => ws.close();
  }, []);

  // Auto-scroll
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [output]);

  const handleRun = async () => {
    try {
      setOutput([]);
      await api.runIndexer();
      loadStatus();
    } catch (e: any) {
      showToast(e.message, true);
    }
  };

  return (
    <>
      <h1 className="page-title">INDEXER</h1>

      <div className="info-grid" style={{ marginBottom: 24 }}>
        <dt>Status</dt>
        <dd>
          <span className={`status-badge ${status?.running ? "running" : "idle"}`}>
            {status?.running ? "RUNNING" : "IDLE"}
          </span>
        </dd>
        <dt>Last Run</dt>
        <dd>{status?.last_run ? new Date(status.last_run).toLocaleString() : "Never"}</dd>
        <dt>Last Result</dt>
        <dd>
          {status?.last_result ? (
            <span className={status.last_result === "success" ? "" : "error"}>
              {status.last_result}
            </span>
          ) : (
            "—"
          )}
        </dd>
        <dt>Files</dt>
        <dd>{status?.file_count ?? "—"}</dd>
        <dt>Categories</dt>
        <dd>{status?.category_count ?? "—"}</dd>
      </div>

      <button className="term-btn" onClick={handleRun} disabled={status?.running}>
        {status?.running ? "[ RUNNING... ]" : "[ RUN NOW ]"}
      </button>

      <h3 style={{ color: "var(--amber)", margin: "24px 0 8px" }}>Output</h3>
      <div className="log-viewer" ref={logRef}>
        {output.map((line, i) => (
          <div key={i} className="log-line">
            {line}
          </div>
        ))}
        {output.length === 0 && (
          <div style={{ color: "var(--dim-green)" }}>
            {status?.running ? "Waiting for output..." : "Press RUN NOW to start the indexer."}
          </div>
        )}
      </div>

      {toast && <div className={`toast ${toast.error ? "error" : ""}`}>{toast.msg}</div>}
    </>
  );
}
