import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { Category, DskMetadata } from "../api";
import { formatSize } from "../utils";
import { useToast } from "../useToast";

export default function UploadPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [area, setArea] = useState("");
  const [dragover, setDragover] = useState(false);
  const [uploading, setUploading] = useState(false);
  const { toast, showToast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  // Extract state
  const [extractMode, setExtractMode] = useState(false);
  const [stagingId, setStagingId] = useState("");
  const [extractedFiles, setExtractedFiles] = useState<{ name: string; size: number; selected: boolean }[]>([]);
  const [dskMetadata, setDskMetadata] = useState<DskMetadata | null>(null);

  // Post-commit state
  const [committed, setCommitted] = useState<string[] | null>(null);

  useEffect(() => {
    api.getCategories().then((cats) => {
      setCategories(cats);
      if (cats.length > 0 && !area) setArea(cats[0].area);
    });
  }, []);

  const isExtractable = (name: string) => {
    const lower = name.toLowerCase();
    return lower.endsWith(".zip") || lower.endsWith(".dsk") || lower.endsWith(".img");
  };

  const handleFiles = useCallback(
    async (fileList: FileList) => {
      if (!area) {
        showToast("Select a category first", true);
        return;
      }
      if (fileList.length === 0) return;

      const file = fileList[0];
      setUploading(true);
      setCommitted(null);

      try {
        if (isExtractable(file.name)) {
          const res = await api.extractArchive(file);
          setStagingId(res.staging_id);
          setExtractedFiles(res.files.map((f) => ({ ...f, selected: true })));
          setDskMetadata(res.dsk_metadata);
          setExtractMode(true);
        } else {
          await api.uploadFile(file, area);
          showToast(`Uploaded ${file.name}`);
        }
      } catch (e: any) {
        showToast(e.message, true);
      } finally {
        setUploading(false);
      }
    },
    [area]
  );

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragover(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleCommit = async () => {
    const selected = extractedFiles.filter((f) => f.selected).map((f) => f.name);
    if (selected.length === 0) {
      showToast("Select at least one file", true);
      return;
    }
    setUploading(true);
    try {
      const res = await api.commitExtract(stagingId, area, selected);
      setCommitted(res.committed);
      setExtractMode(false);
      setExtractedFiles([]);
      setStagingId("");
      setDskMetadata(null);
    } catch (e: any) {
      showToast(e.message, true);
    } finally {
      setUploading(false);
    }
  };

  const toggleFile = (idx: number) => {
    setExtractedFiles((prev) =>
      prev.map((f, i) => (i === idx ? { ...f, selected: !f.selected } : f))
    );
  };

  return (
    <>
      <h1 className="page-title">UPLOAD</h1>

      <div className="search-bar">
        <label>Category:</label>
        <select className="term-select" value={area} onChange={(e) => setArea(e.target.value)}>
          {categories.map((c) => (
            <option key={c.area} value={c.area}>
              {c.display_name}
            </option>
          ))}
        </select>
      </div>

      {/* Post-commit success message */}
      {committed && (
        <div className="editor-panel" style={{ borderColor: "var(--green)" }}>
          <h3 style={{ color: "var(--green)" }}>Committed {committed.length} file(s)</h3>
          <ul style={{ listStyle: "none", padding: 0, margin: "8px 0" }}>
            {committed.map((f) => (
              <li key={f} style={{ color: "var(--green)", fontSize: 13 }}>+ {f}</li>
            ))}
          </ul>
          <div className="editor-actions">
            <Link to="/" className="term-btn" style={{ textDecoration: "none" }}>
              [ VIEW FILES ]
            </Link>
            <button className="term-btn" onClick={() => setCommitted(null)}>
              [ UPLOAD MORE ]
            </button>
          </div>
        </div>
      )}

      {/* Drop zone (hidden when extracting or showing commit result) */}
      {!extractMode && !committed && (
        <>
          <div
            className={`drop-zone ${dragover ? "dragover" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragover(true);
            }}
            onDragLeave={() => setDragover(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
          >
            {uploading
              ? "Analyzing..."
              : "Drop file here or click to browse\n\nZIP, DSK, and IMG files will be extracted for review"}
          </div>
          <input
            ref={fileRef}
            type="file"
            style={{ display: "none" }}
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
          />
        </>
      )}

      {/* Extract review panel */}
      {extractMode && (
        <div className="editor-panel">
          <h3>Extract Review</h3>

          {/* DSK metadata banner */}
          {dskMetadata && (
            <div style={{ marginBottom: 16, padding: "8px 12px", border: "1px solid var(--border)" }}>
              <div style={{ color: "var(--amber)", fontSize: 13, marginBottom: 4 }}>
                Disk Image Detected
              </div>
              <dl className="info-grid" style={{ fontSize: 12 }}>
                <dt>Format</dt>
                <dd>{dskMetadata.display_name}</dd>
                <dt>System</dt>
                <dd>{dskMetadata.system}</dd>
                <dt>Image Size</dt>
                <dd>{formatSize(dskMetadata.image_size)}</dd>
                <dt>Files Found</dt>
                <dd>{dskMetadata.file_count}</dd>
              </dl>
            </div>
          )}

          <p style={{ color: "var(--dim-green)", marginBottom: 12 }}>
            Select files to add to the catalog:
          </p>
          <table className="term-table">
            <thead>
              <tr>
                <th style={{ width: 30 }}></th>
                <th>Filename</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {extractedFiles.map((f, i) => (
                <tr key={f.name} onClick={() => toggleFile(i)} style={{ cursor: "pointer" }}>
                  <td>{f.selected ? "[x]" : "[ ]"}</td>
                  <td>{f.name}</td>
                  <td>{formatSize(f.size)}</td>
                </tr>
              ))}
              {extractedFiles.length === 0 && (
                <tr>
                  <td colSpan={3} style={{ color: "var(--dim-green)" }}>
                    No files found in archive
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="editor-actions" style={{ marginTop: 12 }}>
            <button className="term-btn" onClick={handleCommit} disabled={uploading || extractedFiles.length === 0}>
              [ COMMIT ]
            </button>
            <button
              className="term-btn"
              onClick={() => {
                setExtractMode(false);
                setExtractedFiles([]);
                setDskMetadata(null);
              }}
            >
              [ CANCEL ]
            </button>
          </div>
        </div>
      )}

      {toast && <div className={`toast ${toast.error ? "error" : ""}`}>{toast.msg}</div>}
    </>
  );
}
