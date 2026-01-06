'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { ArrowLeft } from 'lucide-react';
import { generateAiSummary, type AiSummary } from '@/lib/api/error-debug-client';

interface AiSummaryPanelProps {
  query: string;
  results: Array<{
    error_key: string;
    chunks: Array<{
      chunk_id: string;
      function_name: string;
      file_path: string;
    }>;
    match_type: string;
  }>;
  payload: any; // AI payload object
  onBack: () => void;
}

export function AiSummaryPanel({ query, results, payload, onBack }: AiSummaryPanelProps) {
  const [summary, setSummary] = useState<AiSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setSummary(null);

    try {
      const response = await generateAiSummary(payload);
      if (response.ok) {
        setSummary(response.summary);
      } else {
        setError('Failed to generate summary');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to generate AI summary');
      console.error('AI summary generation failed:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-2/3 h-full flex flex-col border-l bg-white overflow-hidden">
      {/* Header */}
      <div className="border-b p-4 bg-white">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={onBack}
              className="flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </Button>
            <h2 className="text-xl font-semibold">AI Summary</h2>
          </div>
          <Button
            onClick={handleGenerate}
            disabled={loading || results.length === 0}
          >
            {loading ? 'Generating...' : 'Generate AI Summary'}
          </Button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="space-y-6">
          {/* Query display */}
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">Query</h3>
            <Card className="p-3">
              <p className="text-sm text-gray-900 break-words whitespace-pre-wrap">{query}</p>
            </Card>
          </div>

          {/* Summary - single heading + box */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-2">Summary</h3>
            <Card className="p-4">
              {error ? (
                <div className="space-y-2">
                  <p className="text-sm text-red-600 font-medium">Error generating summary</p>
                  <p className="text-sm text-red-500">{error}</p>
                </div>
              ) : summary ? (
                <div className="space-y-4">
                  {/* What it means */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-1">What it means</h4>
                    <p className="text-sm text-gray-700">{summary.what_it_means}</p>
                  </div>

                  {/* Most likely cause */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-1">Most likely cause</h4>
                    <p className="text-sm text-gray-700">{summary.most_likely_cause}</p>
                  </div>

                  {/* What to check */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-1">What to check</h4>
                    <ol className="list-decimal list-inside space-y-1">
                      {summary.what_to_check.map((step, idx) => (
                        <li key={idx} className="text-sm text-gray-700">{step}</li>
                      ))}
                    </ol>
                  </div>

                  {/* Where in code */}
                  {summary.where_in_code && summary.where_in_code.length > 0 && (
                    <div>
                      <h4 className="text-sm font-semibold text-gray-900 mb-1">Where in code</h4>
                      <ul className="space-y-2">
                        {summary.where_in_code.map((loc, idx) => (
                          <li key={idx} className="text-sm">
                            <div className="font-medium text-gray-900">
                              {loc.file_path}
                              {loc.lines && ` (lines ${loc.lines})`}
                              {loc.symbol && ` - ${loc.symbol}`}
                            </div>
                            <div className="text-gray-600 text-xs mt-0.5">{loc.why}</div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Confidence */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 mb-1">Confidence</h4>
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-1 rounded text-xs font-medium ${
                          summary.confidence.level === 'high'
                            ? 'bg-green-100 text-green-800'
                            : summary.confidence.level === 'medium'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {summary.confidence.level.toUpperCase()}
                      </span>
                      <span className="text-sm text-gray-600">{summary.confidence.why}</span>
                    </div>
                  </div>
                </div>
              ) : results.length > 0 ? (
                <>
                  <p className="text-sm text-muted-foreground mb-2">
                    AI summary is not generated yet.
                  </p>
                  <p className="text-sm text-muted-foreground">
                    This will summarize across the top results, not just one chunk.
                  </p>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No results available to summarize yet.
                </p>
              )}
            </Card>
          </div>

          {/* Payload display */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-2">Payload (for AI)</h3>
            <Card className="p-4">
              <pre className="text-xs bg-gray-50 p-3 rounded overflow-x-auto whitespace-pre-wrap font-mono">
                {JSON.stringify(payload, null, 2)}
              </pre>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

