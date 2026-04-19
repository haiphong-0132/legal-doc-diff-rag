const CARDS = [
  { key: 'raw_exact', label: 'Giống hệt nhau', color: 'text-green-700 bg-green-50 border-green-200' },
  { key: 'high_confidence_greedy', label: 'Tin cậy cao', color: 'text-blue-700 bg-blue-50 border-blue-200' },
  { key: 'hungarian_hybrid', label: 'Cần phân tích', color: 'text-amber-700 bg-amber-50 border-amber-200' },
  { key: 'llm_items', label: 'LLM đã phân tích', color: 'text-purple-700 bg-purple-50 border-purple-200' },
];

export default function StatsCards({ stats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-5 sm:mb-8">
      {CARDS.map(({ key, label, color }) => (
        <div key={key} className={`rounded-xl border px-3 sm:px-4 py-4 sm:py-5 ${color}`}>
          <p className="text-xl sm:text-2xl font-bold">{stats[key] ?? 0}</p>
          <p className="text-xs sm:text-sm mt-1 opacity-80">{label}</p>
        </div>
      ))}
    </div>
  );
}
