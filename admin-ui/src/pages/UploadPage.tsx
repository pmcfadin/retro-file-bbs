import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Category } from "../api";
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

  useEffect(() => {
    api.getCategories().then((cats) => {
      setCategories(cats);
      if (cats.length > 0 && !area) setArea(cats[0].area);
    });
  }, []);

  const isExtractable = (name: string) => {
    const lower = name.toLowerCase();
    return lower.endsWith(".zip") || lower.endsWith(".dsk");
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

      try {
        if (isExtractable(file.name)) {
          // Extract flow
          const res = await api.extractArchive(file);
          setStagingId(res.staging_id);
          setExtractedFiles(res.files.map((f) => ({ ...f, selected: true })));
          setExtractMode(true);
        } else {
          // Direct upload
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
      showToast(`Committed ${res.committed.length} file(s)`);
      setExtractMode(false);
      setExtractedFiles([]);
      setStagingId("");
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

      {!extractMode && (
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
              ? "Uploading..."
              : "Drop file here or click to browse\n\nZIP and DSK files will be extracted for review"}
          </div>
          <input
            ref={fileRef}
            type="file"
            style={{ display: "none" }}
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
          />
        </>
      )}

      {extractMode && (
        <div className="editor-panel">
          <h3>Extract Review</h3>
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
            </tbody>
          </table>
          <div className="editor-actions" style={{ marginTop: 12 }}>
            <button className="term-btn" onClick={handleCommit} disabled={uploading}>
              [ COMMIT ]
            </button>
            <button
              className="term-btn"
              onClick={() => {
                setExtractMode(false);
                setExtractedFiles([]);
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
