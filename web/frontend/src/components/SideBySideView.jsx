import { useState, useRef, useCallback } from 'react';
import ChangeList from './ChangeList';
import { decodeChunkId } from '../utils/formatId';
import { API_BASE } from '../api';

const MOBILE_TABS = [
  { key: 'vb1', label: 'VB1 — Cũ' },
  { key: 'vb2', label: 'VB2 — Mới' },
  { key: 'results', label: 'Kết quả' },
];

const STAT_ITEMS = [
  { keys: ['giong_nhau_hoan_toan', 'raw_exact'], label: 'Giống hệt', color: 'bg-green-100 text-green-700' },
  { keys: ['giong_nhau_ngu_nghia', 'high_confidence_greedy'], label: 'Giống nghĩa', color: 'bg-blue-100 text-blue-700' },
  { keys: ['sua_doi', 'hungarian_hybrid'], label: 'Sửa đổi', color: 'bg-amber-100 text-amber-700' },
  { keys: ['them_moi'], label: 'Thêm', color: 'bg-emerald-100 text-emerald-700' },
  { keys: ['xoa_bo'], label: 'Xóa', color: 'bg-red-100 text-red-700' },
];

const KIND_BADGE = {
  sua_doi: 'bg-amber-100 text-amber-700',
  them_moi: 'bg-green-100 text-green-700',
  xoa_bo: 'bg-red-100 text-red-700',
  giong_nhau_ngu_nghia: 'bg-blue-100 text-blue-700',
};

const KIND_LABEL = {
  sua_doi: 'Sửa đổi',
  them_moi: 'Thêm mới',
  xoa_bo: 'Xóa bỏ',
  giong_nhau_ngu_nghia: 'Giống ngữ nghĩa',
};

const MIN_COL_PCT = 15; // minimum column width %

/** Drag divider — 12px wide hit area, 2px visible line, dot handle */
function ColDivider({ onMouseDown, active }) {
  const [hovered, setHovered] = useState(false);
  const on = active || hovered;
  return (
    <div
      className="shrink-0 relative flex items-center justify-center cursor-col-resize z-20"
      style={{ width: 12 }}
      onMouseDown={onMouseDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* full-height visible line */}
      <div
        className="absolute inset-y-0 left-1/2 -translate-x-1/2 transition-all duration-100"
        style={{ width: on ? 3 : 2, background: on ? '#3b82f6' : '#d1d5db', borderRadius: 2 }}
      />
      {/* centre grip dots */}
      <div className="relative z-10 flex flex-col gap-[3px]">
        {[0, 1, 2, 3, 4].map(i => (
          <div
            key={i}
            className="rounded-full transition-colors duration-100"
            style={{ width: 4, height: 4, background: on ? '#3b82f6' : '#9ca3af' }}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * SideBySideView — 3-column resizable layout:
 *   Col 1: VB1 (văn bản cũ) — PDF viewer
 *   Col 2: VB2 (văn bản mới) — PDF viewer
 *   Col 3: Kết quả so sánh
 *
 * Two draggable vertical dividers, with a full-screen capture overlay so
 * iframes don't swallow mouse events during drag.
 */
export default function SideBySideView({ jobId, changes, stats }) {
  const [selectedItem, setSelectedItem] = useState(null);
  const [draggingDiv, setDraggingDiv] = useState(0); // 0 = none, 1 or 2
  const [mobileTab, setMobileTab] = useState('results');

  // div1Pos / div2Pos: % from left edge of container
  const posRef = useRef([33, 66]);
  const [pos, setPos] = useState([33, 66]);

  const containerRef = useRef(null);

  const startDrag = useCallback((which) => (e) => {
    e.preventDefault();
    setDraggingDiv(which);

    const onMove = (ev) => {
      if (!containerRef.current) return;
      const { left, width } = containerRef.current.getBoundingClientRect();
      const pct = ((ev.clientX - left) / width) * 100;
      const [p1, p2] = posRef.current;

      let next;
      if (which === 1) {
        const np1 = Math.min(Math.max(pct, MIN_COL_PCT), p2 - MIN_COL_PCT);
        next = [np1, p2];
      } else {
        const np2 = Math.min(Math.max(pct, p1 + MIN_COL_PCT), 100 - MIN_COL_PCT);
        next = [p1, np2];
      }
      posRef.current = next;
      setPos([...next]);
    };

    const onUp = () => {
      setDraggingDiv(0);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, []);

  const [p1, p2] = pos;
  const w1 = p1;
  const w2 = p2 - p1;
  // w3 fills the rest via flex

  const pdfUrl = (doc) => `${API_BASE}/jobs/${jobId}/pdf/${doc}`;
  const vb1Total = stats?.so_luong_chunk_vb1 ?? stats?.vb1_total ?? 0;
  const vb2Total = stats?.so_luong_chunk_vb2 ?? stats?.vb2_total ?? 0;
  const elapsed = stats?.elapsed_s;

  /* ── Shared: selected-item detail panel ─────────────────────────── */
  const selectedDetailPanel = selectedItem && (
    <div className="border-t border-gray-200 bg-gray-50 shrink-0 max-h-64 overflow-y-auto">
      <div className="p-4">
        <div className="flex items-center justify-between mb-2">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${KIND_BADGE[selectedItem.kind]}`}>
            {KIND_LABEL[selectedItem.kind]}
          </span>
          <button
            onClick={() => setSelectedItem(null)}
            className="text-gray-400 hover:text-gray-600 text-sm cursor-pointer"
          >✕</button>
        </div>
        <p className="text-xs text-gray-500 mb-2">
          {selectedItem.kind === 'giong_nhau_ngu_nghia' && selectedItem.vb1_chunk_id && selectedItem.vb2_chunk_id
            ? `${decodeChunkId(selectedItem.vb1_chunk_id)} ↔ ${decodeChunkId(selectedItem.vb2_chunk_id)}`
            : decodeChunkId(selectedItem.vb1_chunk_id || selectedItem.vb2_chunk_id)}
        </p>
        {selectedItem.kind !== 'giong_nhau_ngu_nghia' && selectedItem.summary && (
          <p className="text-xs text-gray-700 mb-2 leading-relaxed">
            <span className="font-semibold">Tóm tắt:</span> {selectedItem.summary}
          </p>
        )}

        {selectedItem.changes?.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-gray-700 mb-1">Chi tiết:</p>
            <div className="space-y-2">
              {selectedItem.changes.map((c, i) =>
                typeof c === 'object' ? (
                  <div key={i} className="text-xs rounded border border-gray-200 overflow-hidden">
                    <div className="flex items-start gap-2 px-2 py-1.5 bg-red-50">
                      <span className="shrink-0 font-semibold text-red-600 mt-0.5">Cũ:</span>
                      <span className="text-gray-700 leading-relaxed whitespace-pre-wrap">{c.old_content}</span>
                    </div>
                    <div className="flex items-start gap-2 px-2 py-1.5 bg-green-50 border-t border-gray-200">
                      <span className="shrink-0 font-semibold text-green-600 mt-0.5">Mới:</span>
                      <span className="text-gray-700 leading-relaxed whitespace-pre-wrap">{c.new_content}</span>
                    </div>
                  </div>
                ) : (
                  <div key={i} className="text-xs rounded border border-gray-150 overflow-hidden bg-white p-2 space-y-1">
                    {String(c).split('\n').map((line, idx) => {
                      if (line.trim().startsWith('Cũ:')) {
                        return (
                          <div key={idx} className="flex items-start gap-1">
                            <span className="shrink-0 font-semibold text-red-600">Cũ:</span>
                            <span className="text-gray-700 leading-relaxed whitespace-pre-wrap">{line.substring(line.indexOf(':') + 1)}</span>
                          </div>
                        );
                      }
                      if (line.trim().startsWith('Mới:')) {
                        return (
                          <div key={idx} className="flex items-start gap-1">
                            <span className="shrink-0 font-semibold text-green-600">Mới:</span>
                            <span className="text-gray-700 leading-relaxed whitespace-pre-wrap">{line.substring(line.indexOf(':') + 1)}</span>
                          </div>
                        );
                      }
                      return (
                        <div key={idx} className="text-gray-600 whitespace-pre-wrap leading-relaxed">{line}</div>
                      );
                    })}
                  </div>
                )
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  /* ── Shared: stats header for results panel ──────────────────────── */
  const statsHeader = stats && (
    <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 shrink-0">
      <p className="text-xs text-gray-400 mb-1.5">
        {vb1Total} chunks VB1 &middot; {vb2Total} chunks VB2
        {elapsed != null && <> &middot; {elapsed}s</>}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {STAT_ITEMS.map(({ keys, label, color }) => (
          <span key={keys[0]} className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
            {readStat(stats, keys)} {label}
          </span>
        ))}
      </div>
    </div>
  );

  return (
    <>
      {/* ── Mobile layout (< md): tabbed single-panel view ───────────── */}
      <div className="md:hidden h-full flex flex-col">
        <div className="shrink-0 flex border-b border-gray-200 bg-white">
          {MOBILE_TABS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setMobileTab(key)}
              className={`flex-1 py-2.5 text-xs font-semibold transition-colors cursor-pointer ${mobileTab === key
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50'
                  : 'text-gray-500 hover:text-gray-700'
                }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex-1 min-h-0">
          {(mobileTab === 'vb1' || mobileTab === 'vb2') && (
            <iframe
              src={pdfUrl(mobileTab)}
              title={mobileTab.toUpperCase()}
              className="w-full h-full border-0 block"
            />
          )}
          {mobileTab === 'results' && (
            <div className="h-full flex flex-col overflow-hidden">
              {statsHeader}
              <div className="flex-1 overflow-hidden" style={{ minHeight: 0 }}>
                <ChangeList changes={changes} onSelect={setSelectedItem} />
              </div>
              {selectedDetailPanel}
            </div>
          )}
        </div>
      </div>

      {/* ── Desktop layout (≥ md): 3-column resizable drag layout ────── */}
      <div
        ref={containerRef}
        className="hidden md:flex h-full"
      >
        {/* Full-screen capture overlay — prevents iframes stealing mousemove during drag */}
        {draggingDiv > 0 && (
          <div className="fixed inset-0 z-50 cursor-col-resize" />
        )}

        {/* ── Col 1: VB1 ──────────────────────────────────────────────────── */}
        <div
          className="flex flex-col rounded-xl border border-gray-200 overflow-hidden bg-white shrink-0"
          style={{ width: `${w1}%`, minWidth: 0 }}
        >
          <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 shrink-0">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">VB1 — Văn bản cũ</span>
          </div>
          <div className="flex-1" style={{ minHeight: 0 }}>
            <iframe src={pdfUrl('vb1')} title="VB1" className="w-full h-full border-0 block" />
          </div>
        </div>

        <ColDivider onMouseDown={startDrag(1)} active={draggingDiv === 1} />

        {/* ── Col 2: VB2 ──────────────────────────────────────────────────── */}
        <div
          className="flex flex-col rounded-xl border border-gray-200 overflow-hidden bg-white shrink-0"
          style={{ width: `${w2}%`, minWidth: 0 }}
        >
          <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 shrink-0">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">VB2 — Văn bản mới</span>
          </div>
          <div className="flex-1" style={{ minHeight: 0 }}>
            <iframe src={pdfUrl('vb2')} title="VB2" className="w-full h-full border-0 block" />
          </div>
        </div>

        <ColDivider onMouseDown={startDrag(2)} active={draggingDiv === 2} />

        {/* ── Col 3: Kết quả so sánh ──────────────────────────────────────── */}
        <div
          className="flex flex-col rounded-xl border border-gray-200 overflow-hidden bg-white"
          style={{ flex: '1 1 0', minWidth: 0 }}
        >
          <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 shrink-0">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Kết quả so sánh</span>
            {stats && (
              <div className="mt-1.5">
                <p className="text-xs text-gray-400 mb-1.5">
                  {vb1Total} chunks VB1 &middot; {vb2Total} chunks VB2
                  {elapsed != null && <> &middot; {elapsed}s</>}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {STAT_ITEMS.map(({ keys, label, color }) => (
                    <span key={keys[0]} className={`text-xs font-semibold px-2 py-0.5 rounded-full ${color}`}>
                      {readStat(stats, keys)} {label}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-hidden" style={{ minHeight: 0 }}>
            <ChangeList changes={changes} onSelect={setSelectedItem} />
          </div>

          {selectedDetailPanel}
        </div>
      </div>
    </>
  );
}

function readStat(stats, keys) {
  for (const key of keys) {
    if (stats?.[key] != null) return stats[key];
  }
  return 0;
}
