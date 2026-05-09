const CARDS = [
  { keys: ['giong_nhau_hoan_toan', 'raw_exact'], label: 'Giống hệt nhau', color: 'text-green-700 bg-green-50 border-green-200' },
  { keys: ['giong_nhau_ngu_nghia', 'high_confidence_greedy'], label: 'Giống ngữ nghĩa', color: 'text-blue-700 bg-blue-50 border-blue-200' },
  { keys: ['sua_doi', 'hungarian_hybrid'], label: 'Sửa đổi', color: 'text-amber-700 bg-amber-50 border-amber-200' },
  { keys: ['them_moi'], label: 'Thêm mới', color: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  { keys: ['xoa_bo'], label: 'Xóa bỏ', color: 'text-red-700 bg-red-50 border-red-200' },
];

function readStat(stats, keys) {
  for (const key of keys) {
    if (stats?.[key] != null) return stats[key];
  }
  return 0;
}

export default function StatsCards({ stats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 sm:gap-4 mb-5 sm:mb-8">
      {CARDS.map(({ keys, label, color }) => (
        <div key={keys[0]} className={`rounded-lg border px-3 sm:px-4 py-4 sm:py-5 ${color}`}>
          <p className="text-xl sm:text-2xl font-bold">{readStat(stats, keys)}</p>
          <p className="text-xs sm:text-sm mt-1 opacity-80">{label}</p>
        </div>
      ))}
    </div>
  );
}
