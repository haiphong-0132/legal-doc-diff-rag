import { useState, useRef } from 'react';
import { startCompare } from '../api';

const ALLOWED = ['.docx', '.pdf'];
const MAX_MB = 20;

function FileDropZone({ label, file, onFile }) {
  const inputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  function validate(f) {
    const ext = '.' + f.name.split('.').pop().toLowerCase();
    if (!ALLOWED.includes(ext)) return `Chỉ chấp nhận ${ALLOWED.join(', ')}`;
    if (f.size > MAX_MB * 1024 * 1024) return `File quá lớn (tối đa ${MAX_MB}MB)`;
    return null;
  }

  function handleFile(f) {
    const err = validate(f);
    if (err) { alert(err); return; }
    onFile(f);
  }

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
      }}
      className={`
        border-2 border-dashed rounded-xl p-5 sm:p-8 text-center cursor-pointer transition-colors
        ${dragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400 bg-white'}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".docx,.pdf"
        className="hidden"
        onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
      />
      <div className="text-4xl mb-3">{file ? '📄' : '📁'}</div>
      <p className="font-medium text-gray-700 mb-1">{label}</p>
      {file ? (
        <div className="text-sm text-green-700 bg-green-50 rounded-lg px-3 py-2 mt-2 inline-block">
          {file.name}
          <span className="text-gray-400 ml-2">
            ({(file.size / 1024).toFixed(0)} KB)
          </span>
        </div>
      ) : (
        <p className="text-sm text-gray-400">
          Kéo thả hoặc click để chọn file (.docx, .pdf)
        </p>
      )}
    </div>
  );
}

export default function UploadPage({ onDone }) {
  const [vb1, setVb1] = useState(null);
  const [vb2, setVb2] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit() {
    if (!vb1 || !vb2) return;
    setLoading(true);
    setError('');
    try {
      const { job_id } = await startCompare(vb1, vb2);
      onDone(job_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-5 sm:mb-8">
        <h2 className="text-xl sm:text-2xl font-bold text-gray-800 mb-2">
          Tải lên hai văn bản để so sánh
        </h2>
        <p className="text-gray-500">
          Hỗ trợ định dạng .docx và .pdf, tối đa {MAX_MB}MB mỗi file
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6 mb-5 sm:mb-8">
        <FileDropZone label="VB1 — Văn bản cũ" file={vb1} onFile={setVb1} />
        <FileDropZone label="VB2 — Văn bản mới" file={vb2} onFile={setVb2} />
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 mb-6 text-sm">
          {error}
        </div>
      )}

      <div className="text-center">
        <button
          onClick={handleSubmit}
          disabled={!vb1 || !vb2 || loading}
          className="w-full sm:w-auto bg-blue-600 text-white px-8 py-3 rounded-lg font-medium
                     hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                     transition-colors cursor-pointer"
        >
          {loading ? 'Đang tải lên...' : 'So sánh'}
        </button>
      </div>
    </div>
  );
}
