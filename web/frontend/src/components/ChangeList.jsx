import { useState } from 'react';
import { decodeChunkId } from '../utils/formatId';
import CompareArrowsIcon from '@mui/icons-material/CompareArrows';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import EditNoteIcon from '@mui/icons-material/EditNote';
import AddCircleOutlinedIcon from '@mui/icons-material/AddCircleOutlined';
import RemoveCircleOutlinedIcon from '@mui/icons-material/RemoveCircleOutlined';

const TABS = [
  { key: 'sua_doi', label: 'Sửa đổi', badge: 'bg-amber-100 text-amber-700', icon: EditNoteIcon, accent: 'border-l-amber-400' },
  { key: 'them_moi', label: 'Thêm mới', badge: 'bg-emerald-100 text-emerald-700', icon: AddCircleOutlinedIcon, accent: 'border-l-emerald-400' },
  { key: 'xoa_bo', label: 'Xóa bỏ', badge: 'bg-red-100 text-red-700', icon: RemoveCircleOutlinedIcon, accent: 'border-l-red-400' },
];

function ChangeCard({ item, onClick, accentClass }) {
  const leftId = item.vb1_chunk_id ? decodeChunkId(item.vb1_chunk_id) : '';
  const rightId = item.vb2_chunk_id ? decodeChunkId(item.vb2_chunk_id) : '';
  const id = item.kind === 'giong_nhau_ngu_nghia' && leftId && rightId ? <>{leftId} <CompareArrowsIcon fontSize="inherit" className="mx-1" /> {rightId}</> : (leftId || rightId);
  const excerpt = item.vb2?.tieu_de || item.vb1?.tieu_de || item.vb2_excerpt || item.vb1_excerpt || item.vb2?.noi_dung || item.vb1?.noi_dung || '';
  const preview = excerpt.length > 120 ? excerpt.slice(0, 120) + '...' : excerpt;

  return (
    <div
      onClick={onClick}
      className={`bg-white border border-slate-200 rounded-xl p-3.5 sm:p-4
                  border-l-[3px] ${accentClass}
                  hover:shadow-md hover:-translate-y-0.5
                  cursor-pointer card-hover`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-slate-800 truncate flex items-center">{id}</div>
          <p className="text-xs text-slate-400 mt-1 line-clamp-2">{preview}</p>
          {item.summary && item.summary !== 'tom tat ngan cac diem thay doi quan trong' && item.summary !== 'Cặp chunk giống nhau về ngữ nghĩa' && (
            <p className="text-xs text-blue-600 mt-2 font-medium">{item.summary}</p>
          )}
        </div>
        <span className="text-slate-300 flex items-center shrink-0">
          {item.kind === 'giong_nhau_ngu_nghia' ? <CompareArrowsIcon style={{ fontSize: 18 }} /> : <ArrowForwardIcon style={{ fontSize: 18 }} />}
        </span>
      </div>
    </div>
  );
}

export default function ChangeList({ changes, onSelect }) {
  const [activeTab, setActiveTab] = useState('sua_doi');
  const items = changes[activeTab] || [];
  const activeTabConfig = TABS.find(t => t.key === activeTab);

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
      <div className="flex border-b border-slate-100 shrink-0 bg-slate-50/50">
        {TABS.map(({ key, label, badge, icon: Icon }) => {
          const count = (changes[key] || []).length;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex-1 flex items-center justify-center gap-1.5 px-2 sm:px-4 py-3 text-xs sm:text-sm font-medium cursor-pointer
                ${activeTab === key
                  ? 'text-indigo-600 border-b-2 border-indigo-600 bg-white'
                  : 'text-slate-400 hover:text-slate-600 hover:bg-white/60'
                }`}
            >
              <Icon style={{ fontSize: 16 }} className={activeTab === key ? 'text-indigo-500' : 'text-slate-300'} />
              {label}
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${activeTab === key ? badge : 'bg-slate-100 text-slate-400'}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-y-auto p-3 sm:p-4" style={{ minHeight: 0 }}>
        {items.length === 0 ? (
          <p className="text-slate-300 text-sm text-center py-8 font-medium">Không có mục nào.</p>
        ) : (
          <div className="space-y-2 sm:space-y-2.5">
            {items.map((item, i) => (
              <ChangeCard
                key={i}
                item={item}
                onClick={() => onSelect(item)}
                accentClass={activeTabConfig?.accent || 'border-l-slate-200'}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
