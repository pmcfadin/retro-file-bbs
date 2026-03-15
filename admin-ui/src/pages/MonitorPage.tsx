import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ConnectionEntry, SessionEntry } from "../api";

export default function MonitorPage() {
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [connections, setConnections] = useState<ConnectionEntry[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);

  // Poll sessions every 5 seconds
  useEffect(() => {
    const load = () => {
      api.getSessions().then(setSessions).catch(console.error);
      api.getConnections().then(setConnections).catch(console.error);
    };
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket for live logs
  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/api/logs`);

    ws.onmessage = (e) => {
      setLogs((prev) => {
        const next = [...prev, e.data];
        if (next.length > 500) next.splice(0, next.length - 500);
        return next;
      });
    };

    ws.onerror = () => console.error("Log WebSocket error");

    return () => {
      ws.close();
    };
  }, []);

  // Auto-scroll log viewer
  useEffect(() => {
    if (autoScroll && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  return (
    <>
      <h1 className="page-title">MONITOR</h1>

      <h3 style={{ color: "var(--amber)", marginBottom: 8 }}>Active Sessions</h3>
      <table className="term-table">
        <thead>
          <tr>
            <th>Session</th>
            <th>IP</th>
            <th>Port</th>
            <th>Connected</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((s) => (
            <tr key={s.session_id}>
              <td>{s.session_id}</td>
              <td>{s.peer_ip}</td>
              <td>{s.peer_port}</td>
              <td>{new Date(s.connected_at).toLocaleTimeString()}</td>
              <td>{s.current_state}</td>
            </tr>
          ))}
          {sessions.length === 0 && (
            <tr>
              <td colSpan={5} style={{ color: "var(--dim-green)" }}>
                No active sessions
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 style={{ color: "var(--amber)", margin: "24px 0 8px" }}>Connection History</h3>
      <table className="term-table">
        <thead>
          <tr>
            <th>Session</th>
            <th>IP</th>
            <th>Event</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {connections
            .slice()
            .reverse()
            .slice(0, 20)
            .map((c, i) => (
              <tr key={`${c.session_id}-${i}`}>
                <td>{c.session_id}</td>
                <td>{c.peer_ip}</td>
                <td>{c.event}</td>
                <td>
                  {new Date(c.connected_at || c.disconnected_at || "").toLocaleTimeString()}
                </td>
              </tr>
            ))}
          {connections.length === 0 && (
            <tr>
              <td colSpan={4} style={{ color: "var(--dim-green)" }}>
                No connection history
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <h3 style={{ color: "var(--amber)", margin: "24px 0 8px" }}>
        Live Logs
        <button
          className="term-btn"
          style={{ marginLeft: 16, fontSize: 11 }}
          onClick={() => setAutoScroll(!autoScroll)}
        >
          {autoScroll ? "[ PAUSE ]" : "[ RESUME ]"}
        </button>
      </h3>
      <div className="log-viewer" ref={logRef}>
        {logs.map((line, i) => (
          <div key={i} className="log-line">
            {line}
          </div>
        ))}
        {logs.length === 0 && (
          <div style={{ color: "var(--dim-green)" }}>Waiting for log output...</div>
        )}
      </div>
    </>
  );
}
