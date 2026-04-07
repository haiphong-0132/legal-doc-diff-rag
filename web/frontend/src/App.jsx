import { useState } from 'react';
import UploadPage from './components/UploadPage';
import ProgressView from './components/ProgressView';
import ResultsPage from './components/ResultsPage';

export default function App() {
  const [step, setStep] = useState('upload');
  const [jobId, setJobId] = useState(null);
  const [results, setResults] = useState(null);

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
    <div className="h-dvh flex flex-col bg-gray-50 overflow-hidden">
      <header className="shrink-0 bg-white border-b border-gray-200 px-4 sm:px-6 py-3 sm:py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-800">
            So sánh Văn bản Pháp lý
          </h1>
          {step !== 'upload' && (
            <button
              onClick={handleReset}
              className="text-sm text-blue-600 hover:text-blue-800 cursor-pointer"
            >
              ← So sánh mới
            </button>
          )}
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
    </div>
  );
}
