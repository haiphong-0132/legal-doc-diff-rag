import CheckCircleOutlinedIcon from '@mui/icons-material/CheckCircleOutlined';
import EditNoteIcon from '@mui/icons-material/EditNote';
import AddCircleOutlinedIcon from '@mui/icons-material/AddCircleOutlined';
import RemoveCircleOutlinedIcon from '@mui/icons-material/RemoveCircleOutlined';

const CARDS = [
  {
    keys: ['giong_nhau_hoan_toan', 'raw_exact'],
    label: 'Giống hệt nhau',
    gradient: 'from-emerald-50 to-green-50',
    border: 'border-l-emerald-500',
    text: 'text-emerald-700',
    icon: CheckCircleOutlinedIcon,
    iconColor: 'text-emerald-300',
  },
  {
    keys: ['sua_doi', 'hungarian_hybrid'],
    label: 'Sửa đổi',
    gradient: 'from-amber-50 to-orange-50',
    border: 'border-l-amber-500',
    text: 'text-amber-700',
    icon: EditNoteIcon,
    iconColor: 'text-amber-300',
  },
  {
    keys: ['them_moi'],
    label: 'Thêm mới',
    gradient: 'from-blue-50 to-indigo-50',
    border: 'border-l-blue-500',
    text: 'text-blue-700',
    icon: AddCircleOutlinedIcon,
    iconColor: 'text-blue-300',
  },
  {
    keys: ['xoa_bo'],
    label: 'Xóa bỏ',
    gradient: 'from-red-50 to-rose-50',
    border: 'border-l-red-500',
    text: 'text-red-700',
    icon: RemoveCircleOutlinedIcon,
    iconColor: 'text-red-300',
  },
];

function readStat(stats, keys) {
  for (const key of keys) {
    if (stats?.[key] != null) return stats[key];
  }
  return 0;
}

export default function StatsCards({ stats }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-5 mb-5 sm:mb-8">
      {CARDS.map(({ keys, label, gradient, border, text, icon: Icon, iconColor }) => (
        <div
          key={keys[0]}
          className={`relative overflow-hidden rounded-xl bg-gradient-to-br ${gradient} border border-slate-100 border-l-[4px] ${border} px-4 py-5 transition-all duration-300 hover:-translate-y-1 hover:shadow-lg shadow-sm`}
        >
          {/* Decorative icon */}
          <div className={`absolute -top-4 -right-4 ${iconColor} opacity-50 transition-transform duration-300 hover:scale-110`}>
            <Icon style={{ fontSize: 96 }} />
          </div>

          <div className="relative z-10">
            <p className={`text-2xl sm:text-3xl font-extrabold tracking-tight ${text}`}>
              {readStat(stats, keys)}
            </p>
            <p className={`text-xs sm:text-sm mt-1.5 font-medium ${text} opacity-80`}>
              {label}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
