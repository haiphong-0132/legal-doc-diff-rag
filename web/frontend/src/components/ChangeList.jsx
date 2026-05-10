import { useState } from 'react';
import { decodeChunkId } from '../utils/formatId';

const TABS = [
  { key: 'sua_doi', label: 'Sửa đổi', badge: 'bg-amber-100 text-amber-700' },
  { key: 'them_moi', label: 'Thêm mới', badge: 'bg-green-100 text-green-700' },
  { key: 'xoa_bo', label: 'Xóa bỏ', badge: 'bg-red-100 text-red-700' },
  { key: 'giong_nhau_ngu_nghia', label: 'Giống ngữ nghĩa', badge: 'bg-blue-100 text-blue-700' },
];

function ChangeCard({ item, onClick }) {
  const leftId = item.vb1_chunk_id ? decodeChunkId(item.vb1_chunk_id) : '';
  const rightId = item.vb2_chunk_id ? decodeChunkId(item.vb2_chunk_id) : '';
  const id = item.kind === 'giong_nhau_ngu_nghia' && leftId && rightId ? `${leftId} ↔ ${rightId}` : (leftId || rightId);
  const excerpt = item.vb2?.tieu_de || item.vb1?.tieu_de || item.vb2_excerpt || item.vb1_excerpt || item.vb2?.noi_dung || item.vb1?.noi_dung || '';
  const preview = excerpt.length > 120 ? excerpt.slice(0, 120) + '...' : excerpt;

  return (
    <div
      onClick={onClick}
      className="bg-white border border-gray-200 rounded-lg p-3 sm:p-4 hover:border-blue-300
                 hover:shadow-sm transition-all cursor-pointer"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">{id}</p>
          <p className="text-xs text-gray-500 mt-1 line-clamp-2">{preview}</p>
          {item.kind !== 'giong_nhau_ngu_nghia' && item.summary && item.summary !== 'tom tat ngan cac diem thay doi quan trong' && (
            <p className="text-xs text-blue-600 mt-2 font-medium">{item.summary}</p>
          )}
        </div>
        <span className="text-gray-300 text-lg shrink-0">{item.kind === 'giong_nhau_ngu_nghia' ? '↔' : '→'}</span>
      </div>
    </div>
  );
}

export default function ChangeList({ changes, onSelect }) {
  const [activeTab, setActiveTab] = useState('sua_doi');
  const items = changes[activeTab] || [];

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-gray-200 overflow-hidden">
      <div className="flex border-b border-gray-200 shrink-0">
        {TABS.map(({ key, label, badge }) => {
          const count = (changes[key] || []).length;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex-1 px-2 sm:px-4 py-2.5 sm:py-3 text-xs sm:text-sm font-medium transition-colors cursor-pointer
                ${activeTab === key
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50/50'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
            >
              {label}
              <span className={`ml-2 text-xs px-1.5 py-0.5 rounded-full ${badge}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto p-3 sm:p-4" style={{ minHeight: 0 }}>
        {items.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-6">Không có mục nào.</p>
        ) : (
          <div className="space-y-2 sm:space-y-3">
            {items.map((item, i) => (
              <ChangeCard key={i} item={item} onClick={() => onSelect(item)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
