'use client';

import { useState } from 'react';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';
import { SearchStrip } from '@/components/SearchStrip';
import { ResultsPane } from '@/components/ResultsPane';
import { DetailsPane } from '@/components/DetailsPane';
import { FilterDrawer } from '@/components/FilterDrawer';
import { searchLibrary, liveScan } from '@/lib/api/client';
import { SearchResult, SearchFilters } from '@/lib/types';

export default function SearchPage() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedOccurrenceId, setSelectedOccurrenceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<SearchFilters>({});

  const handleSearch = async (query: string) => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await searchLibrary(query);
      setResults(data);
    } finally {
      setLoading(false);
    }
  };

  const handleLiveScan = async (query: string) => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await liveScan(query);
      setResults(data);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setResults([]);
    setSelectedOccurrenceId(null);
  };

  return (
    <div className="h-full flex flex-col">
      <SearchStrip
        onSearch={handleSearch}
        onLiveScan={handleLiveScan}
        onClear={handleClear}
        onFiltersClick={() => setFiltersOpen(true)}
        loading={loading}
      />
      <FilterDrawer
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        filters={filters}
        onFiltersChange={setFilters}
      />
      <div className="flex-1 overflow-hidden">
        <PanelGroup direction="horizontal">
          <Panel defaultSize={45} minSize={30}>
            <ResultsPane
              results={results}
              selectedOccurrenceId={selectedOccurrenceId}
              onSelectOccurrence={setSelectedOccurrenceId}
              loading={loading}
            />
          </Panel>
          <PanelResizeHandle className="w-2 bg-border hover:bg-primary/20 transition-colors" />
          <Panel defaultSize={55} minSize={320}>
            <DetailsPane occurrenceId={selectedOccurrenceId} />
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}

