import { NavLink, Route, Routes } from "react-router-dom";
import FilesPage from "./pages/FilesPage";
import UploadPage from "./pages/UploadPage";
import MonitorPage from "./pages/MonitorPage";
import IndexerPage from "./pages/IndexerPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <div className="app-layout">
      <nav className="sidebar">
        <div className="sidebar-title">CPM Depot</div>
        <NavLink to="/" end>
          FILES
        </NavLink>
        <NavLink to="/upload">UPLOAD</NavLink>
        <NavLink to="/monitor">MONITOR</NavLink>
        <NavLink to="/indexer">INDEXER</NavLink>
        <NavLink to="/settings">SETTINGS</NavLink>
        <div className="sidebar-footer">Admin Console v1.0</div>
      </nav>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<FilesPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/monitor" element={<MonitorPage />} />
          <Route path="/indexer" element={<IndexerPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}
