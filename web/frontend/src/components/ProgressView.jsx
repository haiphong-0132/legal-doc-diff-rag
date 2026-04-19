import { useEffect, useState, useRef } from 'react';
import { getJobStatus, getJobResults } from '../api';

const PHASE_ORDER = ['pending', 'loading', 'phase_0', 'phase_1', 'phase_2', 'done'];
const PHASE_LABELS = {
  pending: 'Chờ xử lý',
  loading: 'Đọc văn bản',
  phase_0: 'So sánh text thô',
  phase_1: 'Embedding & Matching',
  phase_2: 'LLM phân tích',
  done: 'Hoàn thành',
};

export default function ProgressView({ jobId, onDone }) {
  const [status, setStatus] = useState({ status: 'pending', phase: '', message: '', error: '' });
  const intervalRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const s = await getJobStatus(jobId);
        if (cancelled) return;
        setStatus(s);

        if (s.status === 'done') {
          clearInterval(intervalRef.current);
          const results = await getJobResults(jobId);
          if (!cancelled) onDone(results);
        } else if (s.status === 'error') {
          clearInterval(intervalRef.current);
        }
      } catch { /* retry on next poll */ }
    }

    poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => { cancelled = true; clearInterval(intervalRef.current); };
  }, [jobId]);

  const currentIdx = PHASE_ORDER.indexOf(status.phase || status.status);
  const pct = Math.max(5, Math.min(100, ((currentIdx + 1) / PHASE_ORDER.length) * 100));

  if (status.status === 'error') {
    return (
      <div className="max-w-xl mx-auto text-center">
        <div className="bg-red-50 border border-red-200 rounded-xl p-5 sm:p-8">
          <div className="text-4xl mb-4">⚠️</div>
          <h3 className="text-lg font-semibold text-red-800 mb-2">Đã xảy ra lỗi</h3>
          <p className="text-red-600 text-sm">{status.error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto text-center">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 sm:p-8">
        <div className="inline-block mb-6">
          <div className="w-16 h-16 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
        </div>
        <h3 className="text-lg font-semibold text-gray-800 mb-2">
          Đang xử lý...
        </h3>
        <p className="text-gray-500 mb-4 sm:mb-6">{status.message || 'Đang khởi tạo pipeline...'}</p>

        <div className="w-full bg-gray-200 rounded-full h-2.5 mb-4">
          <div
            className="bg-blue-600 h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="hidden sm:flex justify-between text-xs text-gray-400">
          {PHASE_ORDER.map((p, i) => (
            <span
              key={p}
              className={i <= currentIdx ? 'text-blue-600 font-medium' : ''}
            >
              {PHASE_LABELS[p]}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
