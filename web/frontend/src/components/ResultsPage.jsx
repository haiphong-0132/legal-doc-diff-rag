import { useState, useRef } from 'react';
import StatsCards from './StatsCards';
import ChangeList from './ChangeList';
import SideBySideView from './SideBySideView';
import { decodeChunkId } from '../utils/formatId';

export default function ResultsPage({ jobId, data }) {
  const [mode, setMode] = useState('results'); // 'results' | 'sidebyside'
  const [selectedItem, setSelectedItem] = useState(null);
  const vb1Total = data.stats.so_luong_chunk_vb1 ?? data.stats.vb1_total ?? 0;
  const vb2Total = data.stats.so_luong_chunk_vb2 ?? data.stats.vb2_total ?? 0;
  const elapsed = data.stats.elapsed_s;

  const toggleBar = (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h2 className="text-xl font-bold text-gray-800 mb-1">Kết quả so sánh</h2>
        {mode === 'results' && (
          <p className="text-sm text-gray-500">
            {vb1Total} chunks VB1 &middot; {vb2Total} chunks VB2
            {elapsed != null && <> &middot; {elapsed}s</>}
          </p>
        )}
      </div>
      <div className="flex rounded-lg border border-gray-200 overflow-hidden text-sm">
        <button
          onClick={() => setMode('results')}
          className={`px-4 py-2 transition-colors cursor-pointer ${mode === 'results' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
        >
          📋 Kết quả
        </button>
        <button
          onClick={() => setMode('sidebyside')}
          className={`px-4 py-2 transition-colors cursor-pointer border-l border-gray-200 ${mode === 'sidebyside' ? 'bg-blue-600 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'}`}
        >
          🗂 Song song
        </button>
      </div>
    </div>
  );

  /* ── Side-by-side: fill all remaining height, minimal padding ── */
  if (mode === 'sidebyside') {
    return (
      <div className="h-full flex flex-col px-3 pt-3 pb-1 gap-2">
        <div className="shrink-0">{toggleBar}</div>
        <div className="flex-1 min-h-0">
          <SideBySideView jobId={jobId} changes={data.changes} stats={data.stats} />
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
            <span className="text-sm text-gray-600">
              {isSemantic && item.vb1_chunk_id && item.vb2_chunk_id
                ? `${decodeChunkId(item.vb1_chunk_id)} ↔ ${decodeChunkId(item.vb2_chunk_id)}`
                : decodeChunkId(item.vb1_chunk_id || item.vb2_chunk_id)}
            </span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl cursor-pointer">✕</button>
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
            </div>
          )}
          {vb2Text && (
            <div className={`p-4 overflow-y-auto ${!vb1Text ? 'col-span-2' : ''}`}>
              <div className="text-xs font-semibold text-gray-400 uppercase mb-2">VB2 (Mới)</div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap select-text">{vb2Text}</p>
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
        {((!isSemantic && item.summary) || item.changes?.length > 0) && (
          <div className="flex-1 overflow-y-auto px-6 py-4 bg-gray-50 rounded-b-2xl">
            {!isSemantic && item.summary && (
              <p className="text-sm text-gray-700 mb-4 leading-relaxed">
                <span className="font-semibold">Tóm tắt:</span> {item.summary}
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
                            <span className="font-semibold text-red-600">Cũ:</span> {c.old_content}
                          </p>
                          <p className="leading-relaxed whitespace-pre-wrap">
                            <span className="font-semibold text-green-600">Mới:</span> {c.new_content}
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          {String(c).split('\n').map((line, idx) => {
                            if (line.trim().startsWith('Cũ:')) {
                              return (
                                <p key={idx} className="leading-relaxed whitespace-pre-wrap">
                                  <span className="font-semibold text-red-600">Cũ:</span>{line.substring(line.indexOf(':') + 1)}
                                </p>
                              );
                            }
                            if (line.trim().startsWith('Mới:')) {
                              return (
                                <p key={idx} className="leading-relaxed whitespace-pre-wrap">
                                  <span className="font-semibold text-green-600">Mới:</span>{line.substring(line.indexOf(':') + 1)}
                                </p>
                              );
                            }
                            return (
                              <p key={idx} className="whitespace-pre-wrap leading-relaxed">{line}</p>
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
