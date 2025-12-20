'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Search, Zap, X, Filter } from 'lucide-react';

interface SearchStripProps {
  onSearch: (query: string) => void;
  onLiveScan: (query: string) => void;
  onClear: () => void;
  onFiltersClick: () => void;
  loading?: boolean;
}

export function SearchStrip({
  onSearch,
  onLiveScan,
  onClear,
  onFiltersClick,
  loading = false,
}: SearchStripProps) {
  const [query, setQuery] = useState('');
  const [normalizedPreview, setNormalizedPreview] = useState('');

  const handleNormalize = (text: string) => {
    // Simple normalization preview (stub)
    setNormalizedPreview(text.toLowerCase().trim().replace(/\s+/g, ' '));
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setQuery(value);
    handleNormalize(value);
  };

  return (
    <div className="border-b bg-white p-4 space-y-3 sticky top-0 z-10">
      <div className="flex gap-2">
        <div className="flex-1">
          <textarea
            value={query}
            onChange={handleChange}
            placeholder="Paste log line or error message here..."
            className="w-full min-h-[80px] p-3 border rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-ring"
            disabled={loading}
          />
        </div>
      </div>
      {normalizedPreview && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">Normalized:</span> {normalizedPreview}
        </div>
      )}
      <div className="flex items-center gap-2">
        <Button onClick={() => onSearch(query)} disabled={!query || loading} className="flex items-center gap-2">
          <Search className="h-4 w-4" />
          Search Library
        </Button>
        <Button
          onClick={() => onLiveScan(query)}
          disabled={!query || loading}
          variant="secondary"
          className="flex items-center gap-2"
        >
          <Zap className="h-4 w-4" />
          Live Scan
        </Button>
        <Button onClick={onClear} variant="ghost" disabled={loading}>
          <X className="h-4 w-4" />
          Clear
        </Button>
        <Button onClick={onFiltersClick} variant="outline" className="flex items-center gap-2">
          <Filter className="h-4 w-4" />
          Filters
        </Button>
      </div>
    </div>
  );
}

