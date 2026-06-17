import { useEffect, useRef, useState } from 'react';
import * as docx from 'docx-preview';
import { API_BASE } from '../api';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import RestartAltIcon from '@mui/icons-material/RestartAlt';

export default function DocViewer({ jobId, docId, path }) {
  const containerRef = useRef(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(0.85);

  const isDocx = path?.toLowerCase().endsWith('.docx');

  useEffect(() => {
    if (!isDocx) {
      setLoading(false);
      return;
    }

    let isMounted = true;
    setLoading(true);

    fetch(`${API_BASE}/jobs/${jobId}/file/${docId}`)
      .then(res => {
        if (!res.ok) throw new Error('Không thể tải file gốc');
        return res.blob();
      })
      .then(blob => {
        if (!isMounted) return;
        return docx.renderAsync(blob, containerRef.current, null, {
          inWrapper: true, 
          ignoreHeight: false, 
          ignoreWidth: false, 
          ignoreFonts: false,
          breakPages: true,
          useBase64URL: true,
        });
      })
      .then(() => {
        if (isMounted) setLoading(false);
      })
      .catch(err => {
        console.error(err);
        if (isMounted) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => { isMounted = false; };
  }, [jobId, docId, isDocx]);

  const handleZoomIn = () => setZoom(z => Math.min(z + 0.1, 2));
  const handleZoomOut = () => setZoom(z => Math.max(z - 0.1, 0.4));
  const handleZoomReset = () => setZoom(0.85);

  if (!isDocx) {
    // Dành cho PDF hoặc định dạng khác
    return (
      <iframe
        src={`${API_BASE}/jobs/${jobId}/pdf/${docId}`}
        title={docId?.toUpperCase()}
        className="w-full h-full border-0 block"
      />
    );
  }

  return (
    <div className="w-full h-full relative bg-[#f3f4f6] overflow-hidden">
      {/* Zoom Controls - Fixed relative to the pane */}
      <div className="absolute top-4 right-6 z-20 flex items-center bg-white border border-slate-200 rounded-lg shadow-md overflow-hidden">
        <button onClick={handleZoomOut} className="p-1.5 text-slate-500 hover:bg-slate-50 hover:text-indigo-600 transition-colors cursor-pointer" title="Thu nhỏ">
          <ZoomOutIcon fontSize="small" />
        </button>
        <span className="text-xs font-medium text-slate-600 px-2 w-12 text-center border-x border-slate-100">
          {Math.round(zoom * 100)}%
        </span>
        <button onClick={handleZoomIn} className="p-1.5 text-slate-500 hover:bg-slate-50 hover:text-indigo-600 transition-colors cursor-pointer" title="Phóng to">
          <ZoomInIcon fontSize="small" />
        </button>
        <button onClick={handleZoomReset} className="p-1.5 text-slate-500 hover:bg-slate-50 hover:text-indigo-600 border-l border-slate-100 transition-colors cursor-pointer" title="Mặc định">
          <RestartAltIcon fontSize="small" />
        </button>
      </div>

      <div className="w-full h-full overflow-auto relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <span className="text-gray-500 font-medium">Đang tải tài liệu gốc...</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-red-500 bg-white z-10 px-4 text-center">
            Lỗi: {error}
          </div>
        )}
        <div
          ref={containerRef}
          className="w-full min-h-full transition-transform origin-top"
          style={{ 
            "--docx-preview-padding": "40px",
            "--docx-preview-background": "#f3f4f6",
            zoom: zoom,
          }}
        />
      </div>
    </div>
  );
}
