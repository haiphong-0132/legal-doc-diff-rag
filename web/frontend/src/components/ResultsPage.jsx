import { useState, useRef } from 'react';
import StatsCards from './StatsCards';
import ChangeList from './ChangeList';
import SideBySideView from './SideBySideView';
import { decodeChunkId } from '../utils/formatId';
import DownloadIcon from '@mui/icons-material/Download';
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf';
import DescriptionIcon from '@mui/icons-material/Description';
import ListAltIcon from '@mui/icons-material/ListAlt';
import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import CloseIcon from '@mui/icons-material/Close';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';

export default function ResultsPage({ jobId, data }) {
  const [mode, setMode] = useState('results'); // 'results' | 'sidebyside'
  const [selectedItem, setSelectedItem] = useState(null);
  const [showExport, setShowExport] = useState(false);
  const vb1Total = data.stats.so_luong_chunk_vb1 ?? data.stats.vb1_total ?? 0;
  const vb2Total = data.stats.so_luong_chunk_vb2 ?? data.stats.vb2_total ?? 0;
  const elapsed = data.stats.elapsed_s;

  const toggleBar = (
    <div className="flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h2 className="text-xl font-extrabold text-slate-800" style={{ fontFamily: 'var(--font-heading)' }}>Kết quả so sánh</h2>
        {mode === 'results' && (
          <p className="text-xs text-slate-400 mt-0.5 font-medium">
            {vb1Total} chunks VB1 &middot; {vb2Total} chunks VB2
            {elapsed != null && <> &middot; {elapsed}s</>}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {/* Export button — standalone */}
        <div className="relative">
          <button
            onClick={() => setShowExport(!showExport)}
            className="flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-lg cursor-pointer
                       bg-gradient-to-r from-indigo-600 to-blue-600 text-white shadow-sm
                       hover:shadow-md hover:shadow-indigo-200"
          >
            <DownloadIcon style={{ fontSize: 16 }} /> Xuất báo cáo <KeyboardArrowDownIcon style={{ fontSize: 16 }} />
          </button>
          {showExport && (
            <div className="absolute top-full right-0 mt-1.5 w-52 bg-white border border-slate-200 rounded-xl shadow-xl z-50 py-1.5 overflow-hidden">
              <a 
                href={`/api/jobs/${jobId}/report?format=pdf`}
                download
                onClick={() => setShowExport(false)}
                className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                <PictureAsPdfIcon style={{ fontSize: 18 }} className="text-red-500" /> Báo cáo PDF
              </a>
              <a 
                href={`/api/jobs/${jobId}/report?format=docx`}
                download
                onClick={() => setShowExport(false)}
                className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                <DescriptionIcon style={{ fontSize: 18 }} className="text-blue-500" /> Báo cáo Word (DOCX)
              </a>
            </div>
          )}
        </div>

        {/* Segmented control */}
        <div className="flex bg-slate-100 rounded-lg p-0.5">
          <button
            onClick={() => setMode('results')}
            className={`flex items-center gap-1 px-3.5 py-2 text-sm font-medium rounded-md cursor-pointer
              ${mode === 'results'
                ? 'bg-white text-indigo-600 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
              }`}
          >
            <ListAltIcon style={{ fontSize: 16 }} /> Kết quả
          </button>
          <button
            onClick={() => setMode('sidebyside')}
            className={`flex items-center gap-1 px-3.5 py-2 text-sm font-medium rounded-md cursor-pointer
              ${mode === 'sidebyside'
                ? 'bg-white text-indigo-600 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
              }`}
          >
            <ViewColumnIcon style={{ fontSize: 16 }} /> Song song
          </button>
        </div>
      </div>
    </div>
  );

  /* ── Side-by-side: fill all remaining height, minimal padding ── */
  if (mode === 'sidebyside') {
    return (
      <div className="h-full flex flex-col px-3 pt-3 pb-1 gap-2">
        <div className="shrink-0">{toggleBar}</div>
        <div className="flex-1 min-h-0">
          <SideBySideView jobId={jobId} data={data} changes={data.changes} stats={data.stats} />
        </div>
      </div>
    );
  }

  /* ── Results mode: scrollable, max-width container ── */
  return (
    <div className="h-full overflow-auto">
      <div className="w-full px-4 sm:px-8 py-6">
        <div className="mb-6">{toggleBar}</div>
        <StatsCards stats={data.stats} />
        <ChangeList changes={data.changes} onSelect={setSelectedItem} />
        {selectedItem && (
          <ChangeDetailModal item={selectedItem} onClose={() => setSelectedItem(null)} />
        )}
      </div>
    </div>
  );
}

/* Small inline modal for results mode */
function ChangeDetailModal({ item, onClose }) {
  const vb1Text = item.vb1?.noi_dung || item.vb1_excerpt || '';
  const vb2Text = item.vb2?.noi_dung || item.vb2_excerpt || '';
  const isSemantic = item.kind === 'giong_nhau_ngu_nghia';
  const hasLlmContent = (!isSemantic && item.summary) || (item.changes && item.changes.length > 0);

  // Chiều cao mặc định của phần nội dung văn bản (220px)
  const [topHeight, setTopHeight] = useState(220);
  const isDragging = useRef(false);

  const handleMouseDown = (e) => {
    e.preventDefault();
    isDragging.current = true;
    const startY = e.clientY;
    const startHeight = topHeight;

    const handleMouseMove = (moveEvent) => {
      if (!isDragging.current) return;
      const deltaY = moveEvent.clientY - startY;
      const newHeight = startHeight + deltaY;
      // Khống chế chiều cao tối thiểu 80px và tối đa 500px
      setTopHeight(Math.max(80, Math.min(newHeight, 500)));
    };

    const handleMouseUp = () => {
      isDragging.current = false;
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleTouchStart = (e) => {
    isDragging.current = true;
    const startY = e.touches[0].clientY;
    const startHeight = topHeight;

    const handleTouchMove = (moveEvent) => {
      if (!isDragging.current) return;
      const deltaY = moveEvent.touches[0].clientY - startY;
      const newHeight = startHeight + deltaY;
      setTopHeight(Math.max(80, Math.min(newHeight, 500)));
    };

    const handleTouchEnd = () => {
      isDragging.current = false;
      window.removeEventListener('touchmove', handleTouchMove);
      window.removeEventListener('touchend', handleTouchEnd);
    };

    window.addEventListener('touchmove', handleTouchMove);
    window.addEventListener('touchend', handleTouchEnd);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full h-[80vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
          <div>
            <span className={`text-xs font-semibold px-2 py-1 rounded-full mr-3 ${kindStyle(item.kind)}`}>
              {kindLabel(item.kind)}
            </span>
            <span className="text-sm text-gray-600 flex items-center inline-flex">
              {isSemantic && item.vb1_chunk_id && item.vb2_chunk_id
                ? <>{decodeChunkId(item.vb1_chunk_id)} <CompareArrowsIcon fontSize="inherit" className="mx-1" /> {decodeChunkId(item.vb2_chunk_id)}</>
                : decodeChunkId(item.vb1_chunk_id || item.vb2_chunk_id)}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl cursor-pointer"><CloseIcon /></button>
        </div>

        {/* Phần nội dung điều khoản có chiều cao có thể co giãn động hoặc phủ kín nếu không có báo cáo LLM */}
        <div 
          style={hasLlmContent ? { height: `${topHeight}px` } : undefined}
          className={`grid grid-cols-2 gap-0 border-b border-gray-200 overflow-hidden ${hasLlmContent ? 'shrink-0' : 'flex-1'}`}
        >
          {vb1Text && (
            <div className={`p-4 overflow-y-auto ${!vb2Text ? 'col-span-2' : 'border-r border-gray-200'}`}>
              <div className="text-xs font-semibold text-gray-400 uppercase mb-2">VB1 (Cũ)</div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap select-text">{vb1Text}</p>
              {renderTables(item.vb1?.tables)}
            </div>
          )}
          {vb2Text && (
            <div className={`p-4 overflow-y-auto ${!vb1Text ? 'col-span-2' : ''}`}>
              <div className="text-xs font-semibold text-gray-400 uppercase mb-2">VB2 (Mới)</div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap select-text">{vb2Text}</p>
              {renderTables(item.vb2?.tables)}
            </div>
          )}
        </div>

        {/* Thanh phân chia kéo thả ngang (Horizontal Divider Bar) - Chỉ hiển thị nếu có báo cáo LLM */}
        {hasLlmContent && (
          <div 
            onMouseDown={handleMouseDown}
            onTouchStart={handleTouchStart}
            className="h-2 w-full bg-gray-100 hover:bg-indigo-200 active:bg-indigo-300 cursor-ns-resize flex items-center justify-center select-none transition-colors duration-150 border-b border-gray-200 shrink-0"
            title="Kéo thả lên/xuống để điều chỉnh chiều cao"
          >
            <div className="w-16 h-1 bg-gray-300 rounded-full hover:bg-gray-400 transition-colors"></div>
          </div>
        )}

        {/* Phần kết quả so sánh LLM chiếm trọn không gian còn lại và tự cuộn */}
        {(item.summary || item.changes?.length > 0) && (
          <div className="flex-1 overflow-y-auto px-6 py-4 bg-gray-50 rounded-b-2xl">
            {item.summary && (
              <p className="text-sm text-gray-700 mb-4 leading-relaxed">
                <span className="font-semibold">{isSemantic ? 'Ghi chú:' : 'Tóm tắt:'}</span> {item.summary}
              </p>
            )}
            {item.changes?.length > 0 && (
              <div>
                <span className="text-sm font-semibold text-gray-700 block mb-2">Chi tiết thay đổi:</span>
                <ul className="text-sm text-gray-600 space-y-2">
                  {item.changes.map((c, i) => (
                    <li key={i} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
                      {typeof c === 'object' ? (
                        <div className="space-y-1">
                          <p className="leading-relaxed whitespace-pre-wrap">
                            <span className="font-semibold text-red-600">Cũ:</span> {renderRich(c.old_content)}
                          </p>
                          <p className="leading-relaxed whitespace-pre-wrap">
                            <span className="font-semibold text-green-600">Mới:</span> {renderRich(c.new_content)}
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          {String(c).split('\n').map((line, idx) => {
                            if (line.trim().startsWith('Cũ:')) {
                              return (
                                <p key={idx} className="leading-relaxed whitespace-pre-wrap">
                                  <span className="font-semibold text-red-600">Cũ:</span>{renderRich(line.substring(line.indexOf(':') + 1))}
                                </p>
                              );
                            }
                            if (line.trim().startsWith('Mới:')) {
                              return (
                                <p key={idx} className="leading-relaxed whitespace-pre-wrap">
                                  <span className="font-semibold text-green-600">Mới:</span>{renderRich(line.substring(line.indexOf(':') + 1))}
                                </p>
                              );
                            }
                            return (
                              <p key={idx} className="whitespace-pre-wrap leading-relaxed">{renderRich(line)}</p>
                            );
                          })}
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Render danh sách bảng (HTML gốc) thành <table> thật thay vì text flatten.
function renderTables(tables) {
  if (!tables || tables.length === 0) return null;
  return (
    <div className="mt-3 space-y-3">
      <div className="text-xs font-semibold text-gray-400 uppercase">Bảng biểu</div>
      {tables.map((html, i) => (
        <div
          key={i}
          className="overflow-x-auto text-xs border border-gray-200 rounded
                     [&_table]:w-full [&_table]:border-collapse
                     [&_td]:border [&_td]:border-gray-300 [&_td]:px-2 [&_td]:py-1 [&_td]:align-top
                     [&_th]:border [&_th]:border-gray-300 [&_th]:px-2 [&_th]:py-1 [&_th]:bg-gray-100 [&_th]:text-left"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ))}
    </div>
  );
}

// Render text có đánh dấu **...** (Markdown bold) -> <strong> tô nổi bật từ thay đổi.
function renderRich(text) {
  if (text == null) return null;
  const parts = String(text).split(/\*\*(.+?)\*\*/g);
  return parts.map((p, i) =>
    i % 2 === 1
      ? <strong key={i} className="font-bold text-blue-700 bg-blue-50 rounded px-0.5">{p}</strong>
      : <span key={i}>{p}</span>
  );
}

function kindLabel(kind) {
  return {
    sua_doi: 'Sửa đổi',
    them_moi: 'Thêm mới',
    xoa_bo: 'Xóa bỏ',
    giong_nhau_ngu_nghia: 'Giống ngữ nghĩa',
  }[kind] || kind;
}
function kindStyle(kind) {
  return {
    sua_doi: 'bg-amber-100 text-amber-700',
    them_moi: 'bg-green-100 text-green-700',
    xoa_bo: 'bg-red-100 text-red-700',
    giong_nhau_ngu_nghia: 'bg-blue-100 text-blue-700',
  }[kind] || 'bg-gray-100 text-gray-600';
}
