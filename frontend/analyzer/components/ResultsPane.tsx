'use client';

import { useState } from 'react';
import { SearchResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ResultsPaneProps {
  results: SearchResult[];
  selectedOccurrenceId: string | null;
  onSelectOccurrence: (occurrenceId: string) => void;
  loading?: boolean;
}

export function ResultsPane({
  results,
  selectedOccurrenceId,
  onSelectOccurrence,
  loading = false,
}: ResultsPaneProps) {
  // Groups collapsed by default
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [sortBy, setSortBy] = useState<'confidence' | 'recent'>('confidence');

  const toggleGroup = (errorKey: string) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(errorKey)) {
      newExpanded.delete(errorKey);
    } else {
      newExpanded.add(errorKey);
    }
    setExpandedGroups(newExpanded);
  };

  const expandAll = () => {
    setExpandedGroups(new Set(results.map((r) => r.errorKey)));
  };

  const collapseAll = () => {
    setExpandedGroups(new Set());
  };

  if (loading) {
    return (
      <div className="p-4 text-center text-muted-foreground">Searching...</div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="p-4 text-center text-muted-foreground">
        No results found. Try a different search query.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="border-b p-4 flex items-center justify-between bg-white">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">
            {results.length} {results.length === 1 ? 'group' : 'groups'}
          </span>
          <Button variant="ghost" size="sm" onClick={expandAll}>
            Expand All
          </Button>
          <Button variant="ghost" size="sm" onClick={collapseAll}>
            Collapse All
          </Button>
        </div>
        <Select value={sortBy} onValueChange={(v) => setSortBy(v as 'confidence' | 'recent')}>
          <SelectTrigger className="w-[150px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="confidence">Sort by Confidence</SelectItem>
            <SelectItem value="recent">Sort by Recent</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-3">
        {results.map((result) => {
          const isExpanded = expandedGroups.has(result.errorKey);
          const topMatch = result.occurrences[0];
          const remainingCount = result.totalCount - 1;

          return (
            <Card key={result.errorKey} className="overflow-hidden">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-semibold">
                    {result.errorKey}
                  </CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => toggleGroup(result.errorKey)}
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                {/* Always show top match */}
                {topMatch && (
                  <div
                    className={cn(
                      'p-3 rounded border cursor-pointer transition-colors',
                      selectedOccurrenceId === topMatch.id
                        ? 'bg-primary/10 border-primary'
                        : 'bg-muted/50 hover:bg-muted'
                    )}
                    onClick={() => onSelectOccurrence(topMatch.id)}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium">
                        {topMatch.filePath}:{topMatch.lineNumber}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {(topMatch.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground font-mono truncate">
                      {topMatch.context}
                    </div>
                  </div>
                )}
                {/* View all button when collapsed */}
                {!isExpanded && remainingCount > 0 && (
                  <Button
                    variant="link"
                    className="w-full mt-2"
                    onClick={() => toggleGroup(result.errorKey)}
                  >
                    View all ({remainingCount + 1})
                  </Button>
                )}
                {/* Expanded view shows all occurrences */}
                {isExpanded && (
                  <div className="mt-3 space-y-2">
                    {result.occurrences.slice(1).map((occ) => (
                      <div
                        key={occ.id}
                        className={cn(
                          'p-3 rounded border cursor-pointer transition-colors',
                          selectedOccurrenceId === occ.id
                            ? 'bg-primary/10 border-primary'
                            : 'bg-muted/50 hover:bg-muted'
                        )}
                        onClick={() => onSelectOccurrence(occ.id)}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium">
                            {occ.filePath}:{occ.lineNumber}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {(occ.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="text-xs text-muted-foreground font-mono truncate">
                          {occ.context}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

