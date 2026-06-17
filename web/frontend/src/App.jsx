import { useState, useEffect } from 'react';
import UploadPage from './components/UploadPage';
import ProgressView from './components/ProgressView';
import ResultsPage from './components/ResultsPage';
import FloatingTimer from './components/FloatingTimer';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';

export default function App() {
  const [step, setStep] = useState(() => {
    return sessionStorage.getItem('diff_step') || 'upload';
  });
  const [jobId, setJobId] = useState(() => {
    return sessionStorage.getItem('diff_job_id') || null;
  });
  const [results, setResults] = useState(() => {
    const saved = sessionStorage.getItem('diff_results');
    try {
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    sessionStorage.setItem('diff_step', step);
  }, [step]);

  useEffect(() => {
    if (jobId) {
      sessionStorage.setItem('diff_job_id', jobId);
    } else {
      sessionStorage.removeItem('diff_job_id');
    }
  }, [jobId]);

  useEffect(() => {
    if (results) {
      sessionStorage.setItem('diff_results', JSON.stringify(results));
    } else {
      sessionStorage.removeItem('diff_results');
    }
  }, [results]);

  function handleUploadDone(id) {
    setJobId(id);
    setStep('progress');
  }

  function handlePipelineDone(data) {
    setResults(data);
    setStep('results');
  }

  function handleReset() {
    setJobId(null);
    setResults(null);
    setStep('upload');
  }

  return (
    <div className="h-dvh flex flex-col bg-slate-50 overflow-hidden">
      {/* ── Premium Light Topbar ── */}
      <header className="shrink-0 relative z-10 bg-white border-b border-slate-200 shadow-[0_4px_20px_-10px_rgba(0,0,0,0.05)]">
        <div className="px-4 sm:px-6 lg:px-8 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-slate-50 p-1.5 rounded-xl border border-slate-100 shadow-sm">
                <img src="/logo.svg" alt="PTIT Logo" className="w-8 h-8 object-contain" />
              </div>
              <div>
                <h1 className="text-lg font-bold text-slate-800 tracking-tight leading-tight" style={{ fontFamily: 'var(--font-heading)' }}>
                  So sánh Văn bản Pháp lý
                </h1>
                <p className="text-[11px] text-slate-500 font-medium tracking-wide">
                  Hệ thống phân tích & đối chiếu văn bản
                </p>
              </div>
            </div>
            {step !== 'upload' && (
              <button
                onClick={handleReset}
                className="flex items-center gap-1.5 text-sm text-slate-600 bg-white hover:bg-slate-50 hover:text-slate-800 px-3.5 py-2 rounded-lg cursor-pointer border border-slate-200 shadow-sm transition-all"
              >
                <ArrowBackIcon style={{ fontSize: 16 }} />
                <span className="hidden sm:inline">So sánh mới</span>
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-hidden">
        {step === 'upload' && (
          <div className="h-full overflow-auto">
            <div className="max-w-7xl mx-auto px-4 py-4 sm:py-8">
              <UploadPage onDone={handleUploadDone} />
            </div>
          </div>
        )}
        {step === 'progress' && (
          <div className="h-full overflow-auto">
            <div className="max-w-7xl mx-auto px-4 py-4 sm:py-8">
              <ProgressView jobId={jobId} onDone={handlePipelineDone} />
            </div>
          </div>
        )}
        {step === 'results' && (
          <ResultsPage jobId={jobId} data={results} />
        )}
      </main>
      <FloatingTimer step={step} results={results} />
    </div>
  );
}
