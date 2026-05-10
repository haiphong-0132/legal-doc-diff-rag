import { useState, useEffect, useRef } from 'react';

export default function FloatingTimer({ step, results }) {
  const [isOpen, setIsOpen] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const intervalRef = useRef(null);

  // Lấy thời gian bắt đầu từ sessionStorage hoặc khởi tạo mới
  const getStartTime = () => {
    const saved = sessionStorage.getItem('diff_start_time');
    if (saved) return parseInt(saved, 10);
    return null;
  };

  useEffect(() => {
    // Nếu chuyển về màn hình tải file, reset bộ đếm
    if (step === 'upload') {
      sessionStorage.removeItem('diff_start_time');
      setElapsed(0);
      setIsOpen(false);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    // Nếu đang chạy (progress), khởi chạy interval đếm thời gian thực
    if (step === 'progress') {
      let startTime = getStartTime();
      if (!startTime) {
        startTime = Date.now();
        sessionStorage.setItem('diff_start_time', startTime.toString());
      }
      
      // Mở rộng giao diện hiển thị bộ đếm tự động khi bắt đầu chạy
      setIsOpen(true);

      if (intervalRef.current) clearInterval(intervalRef.current);

      intervalRef.current = setInterval(() => {
        const currentStartTime = getStartTime();
        if (currentStartTime) {
          setElapsed(Date.now() - currentStartTime);
        }
      }, 100); // cập nhật mỗi 100ms (1/10 giây)
    }

    // Nếu đã có kết quả (results), đóng băng bộ đếm ở thời điểm hoàn thành
    if (step === 'results') {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      
      const startTime = getStartTime();
      if (startTime && results?.stats?.elapsed_s) {
        // Sử dụng thời gian hoàn thành thực tế từ backend hoặc tính toán dựa trên mốc bắt đầu
        const calculatedElapsed = Date.now() - startTime;
        // Ưu tiên thời gian đo bởi Backend nếu khả dụng
        setElapsed(results.stats.elapsed_s * 1000);
      } else if (startTime) {
        setElapsed(Date.now() - startTime);
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [step, results]);

  // Nếu đang ở màn hình upload (chưa chạy), không hiển thị widget
  if (step === 'upload') return null;

  // Định dạng thời gian thành dạng MM:SS.m (Phút:Giây.Phần mười giây)
  const formatTime = (ms) => {
    const totalSeconds = ms / 1000;
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = Math.floor(totalSeconds % 60);
    const tenths = Math.floor((ms % 1000) / 100);

    const pad = (num) => String(num).padStart(2, '0');
    return `${pad(minutes)}:${pad(seconds)}.${tenths}`;
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center select-none font-sans">
      {/* Container của widget trượt ngang - Thiết kế Thủy tinh màu ĐEN (Dark Glassmorphism) cực ngầu */}
      <div
        className={`flex items-center overflow-hidden transition-all duration-300 ease-in-out shadow-2xl rounded-full backdrop-blur-md border ${
          isOpen
            ? 'max-w-xs px-4 bg-slate-950/90 border-slate-800 text-white h-12'
            : 'max-w-0 px-0 bg-transparent border-transparent h-12 shadow-none'
        }`}
      >
        <div className="flex items-center gap-3 whitespace-nowrap">
          <span className="flex h-2 w-2 relative">
            {step === 'progress' && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            )}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${step === 'progress' ? 'bg-emerald-500' : 'bg-slate-500'}`}></span>
          </span>
          <div className="flex flex-col justify-center">
            <span className="text-[10px] text-slate-400 font-medium uppercase tracking-wider leading-none mb-0.5">
              {step === 'progress' ? 'Đang phân tích' : 'Thời gian chạy'}
            </span>
            <span className={`font-mono text-sm font-bold tracking-wider ${step === 'progress' ? 'text-emerald-400' : 'text-slate-200'}`}>
              {formatTime(elapsed)}
            </span>
          </div>
          {results?.stats?.elapsed_s && step === 'results' && (
            <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-medium">
              API: {results.stats.elapsed_s.toFixed(2)}s
            </span>
          )}
          <button
            onClick={() => setIsOpen(false)}
            className="ml-2 p-1 text-slate-400 hover:text-white hover:bg-slate-800 rounded-full cursor-pointer transition-colors"
            title="Thu nhỏ bộ đếm"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Icon đồng hồ nổi tròn - Thiết kế Thủy tinh (Glassmorphism) màu trắng mờ tinh tế */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className={`w-12 h-12 rounded-full flex items-center justify-center cursor-pointer transition-all duration-300 backdrop-blur-md border shadow-lg hover:scale-105 active:scale-95 bg-white/30 border-white/60 text-slate-500 hover:bg-white/60 hover:text-slate-700 hover:border-white/80 shadow-slate-200/20 ${
            step === 'progress' ? 'animate-pulse' : ''
          }`}
          title="Xem thời gian xử lý"
        >
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            ></path>
          </svg>
        </button>
      )}
    </div>
  );
}
