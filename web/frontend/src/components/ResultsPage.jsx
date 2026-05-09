import { useState } from 'react';
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
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

        <div className="grid grid-cols-2 gap-0 flex-1 overflow-hidden">
          {vb1Text && (
            <div className={`p-5 overflow-y-auto ${!vb2Text ? 'col-span-2' : 'border-r border-gray-200'}`}>
              <div className="text-xs font-semibold text-gray-400 uppercase mb-2">VB1 (Cũ)</div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{vb1Text}</p>
            </div>
          )}
          {vb2Text && (
            <div className={`p-5 overflow-y-auto ${!vb1Text ? 'col-span-2' : ''}`}>
              <div className="text-xs font-semibold text-gray-400 uppercase mb-2">VB2 (Mới)</div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{vb2Text}</p>
            </div>
          )}
        </div>

        {((!isSemantic && item.summary) || item.changes?.length > 0) && (
          <div className="border-t border-gray-200 px-6 py-4 bg-gray-50 rounded-b-2xl">
            {!isSemantic && item.summary && (
              <p className="text-sm text-gray-700 mb-2">
                <span className="font-medium">Tóm tắt:</span> {item.summary}
              </p>
            )}
            {item.changes?.length > 0 && (
              <div>
                <span className="text-sm font-medium text-gray-700">Chi tiết thay đổi:</span>
                <ul className="text-sm text-gray-600 mt-2 space-y-2">
                  {item.changes.map((c, i) => (
                    <li key={i} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
                      {typeof c === 'object' ? (
                        <div className="space-y-2">
                          <p className="leading-relaxed">
                            <span className="font-semibold text-red-600">Cũ:</span> {c.old_content}
                          </p>
                          <p className="leading-relaxed">
                            <span className="font-semibold text-green-600">Mới:</span> {c.new_content}
                          </p>
                        </div>
                      ) : (
                        <p className="whitespace-pre-line leading-relaxed">{c}</p>
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
