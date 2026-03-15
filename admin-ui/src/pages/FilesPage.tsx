import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Category, FileEntry } from "../api";
import { formatSize } from "../utils";
import { useToast } from "../useToast";

function relPath(f: FileEntry): string {
  return `${f.area}/${f.filename}`;
}

export default function FilesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [area, setArea] = useState("");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [selected, setSelected] = useState<FileEntry | null>(null);

  // Editor state
  const [editDesc, setEditDesc] = useState("");
  const [editArea, setEditArea] = useState("");
  const [saving, setSaving] = useState(false);
  const { toast, showToast } = useToast();
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    api.getCategories().then(setCategories).catch(console.error);
  }, []);

  const loadFiles = useCallback(() => {
    api.getFiles({ area: area || undefined, search: search || undefined, page, per_page: 50 })
      .then((res) => {
        setFiles(res.files);
        setTotal(res.total);
        setTotalPages(res.total_pages);
      })
      .catch(console.error);
  }, [area, search, page]);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const handleSelect = (f: FileEntry) => {
    setSelected(f);
    setEditDesc(f.description || "");
    setEditArea(f.area);
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      await api.patchFile(relPath(selected), { description: editDesc, area: editArea });
      showToast("File updated");
      setSelected(null);
      loadFiles();
    } catch (e: any) {
      showToast(e.message, true);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selected) return;
    try {
      await api.deleteFile(relPath(selected));
      showToast("File deleted");
      setSelected(null);
      setConfirmDelete(false);
      loadFiles();
    } catch (e: any) {
      showToast(e.message, true);
      setConfirmDelete(false);
    }
  };

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(1);
  };

  return (
    <>
      <h1 className="page-title">FILES</h1>

      <div className="search-bar">
        <label>&gt; search:</label>
        <input
          className="term-input"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          placeholder="filename or description..."
          style={{ width: 250 }}
        />
        <button className="term-btn" onClick={handleSearch}>
          [ SEARCH ]
        </button>
        {search && (
          <button
            className="term-btn"
            onClick={() => {
              setSearch("");
              setSearchInput("");
              setPage(1);
            }}
          >
            [ CLEAR ]
          </button>
        )}

        <select
          className="term-select"
          value={area}
          onChange={(e) => {
            setArea(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c.area} value={c.area}>
              {c.display_name} ({c.count})
            </option>
          ))}
        </select>
      </div>

      <table className="term-table">
        <thead>
          <tr>
            <th>Filename</th>
            <th>Category</th>
            <th>Size</th>
            <th>Description</th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr
              key={f.path}
              className={selected?.path === f.path ? "selected" : ""}
              onClick={() => handleSelect(f)}
              style={{ cursor: "pointer" }}
            >
              <td>{f.filename}</td>
              <td>{f.area}</td>
              <td>{formatSize(f.size)}</td>
              <td>{(f.description || "").split("\n")[0].slice(0, 60)}</td>
            </tr>
          ))}
          {files.length === 0 && (
            <tr>
              <td colSpan={4} style={{ color: "var(--dim-green)" }}>
                No files found.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="pagination">
        <button className="term-btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          [ PREV ]
        </button>
        <span>
          Page {page} of {totalPages} ({total} files)
        </span>
        <button className="term-btn" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
          [ NEXT ]
        </button>
      </div>

      {selected && (
        <div className="editor-panel">
          <h3>Edit: {selected.filename}</h3>
          <div className="editor-field">
            <label>Description</label>
            <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
          </div>
          <div className="editor-field">
            <label>Category</label>
            <select className="term-select" value={editArea} onChange={(e) => setEditArea(e.target.value)}>
              {categories.map((c) => (
                <option key={c.area} value={c.area}>
                  {c.display_name}
                </option>
              ))}
            </select>
          </div>
          <div className="editor-actions">
            <button className="term-btn" onClick={handleSave} disabled={saving}>
              [ SAVE ]
            </button>
            <button className="term-btn danger" onClick={() => setConfirmDelete(true)}>
              [ DELETE ]
            </button>
            <button className="term-btn" onClick={() => setSelected(null)}>
              [ CANCEL ]
            </button>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div className="confirm-overlay">
          <div className="confirm-box">
            <p>Delete {selected?.filename}? This cannot be undone.</p>
            <div className="confirm-actions">
              <button className="term-btn danger" onClick={handleDelete}>
                [ CONFIRM ]
              </button>
              <button className="term-btn" onClick={() => setConfirmDelete(false)}>
                [ CANCEL ]
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && <div className={`toast ${toast.error ? "error" : ""}`}>{toast.msg}</div>}
    </>
  );
}
