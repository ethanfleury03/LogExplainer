'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { X } from 'lucide-react';
import { SearchFilters } from '@/lib/types';

interface FilterDrawerProps {
  open: boolean;
  onClose: () => void;
  filters: SearchFilters;
  onFiltersChange: (filters: SearchFilters) => void;
}

export function FilterDrawer({ open, onClose, filters, onFiltersChange }: FilterDrawerProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose}>
      <div
        className="absolute right-0 top-0 h-full w-[400px] bg-white shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <Card className="h-full rounded-none border-0">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Filters</CardTitle>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium">Min Confidence</label>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.1"
                  value={filters.minConfidence || ''}
                  onChange={(e) =>
                    onFiltersChange({
                      ...filters,
                      minConfidence: e.target.value ? parseFloat(e.target.value) : undefined,
                    })
                  }
                  className="w-full mt-1 p-2 border rounded"
                />
              </div>
              <div>
                <label className="text-sm font-medium">File Path</label>
                <input
                  type="text"
                  value={filters.filePath || ''}
                  onChange={(e) =>
                    onFiltersChange({ ...filters, filePath: e.target.value || undefined })
                  }
                  className="w-full mt-1 p-2 border rounded"
                  placeholder="/opt/memjet/..."
                />
              </div>
              <div>
                <label className="text-sm font-medium">Function Name</label>
                <input
                  type="text"
                  value={filters.functionName || ''}
                  onChange={(e) =>
                    onFiltersChange({ ...filters, functionName: e.target.value || undefined })
                  }
                  className="w-full mt-1 p-2 border rounded"
                  placeholder="waitComplete"
                />
              </div>
              <Button onClick={onClose} className="w-full">
                Apply Filters
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

