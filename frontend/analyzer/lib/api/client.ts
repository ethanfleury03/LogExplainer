import {
  IndexStatus,
  ErrorKey,
  SearchResult,
  SearchFilters,
  OccurrenceDetail,
  Occurrence,
} from '../types';

// Stub data generators
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const STUB_INDEXES: IndexStatus[] = [
  { id: 'all', name: 'All Indexes', status: 'healthy', lastBuilt: new Date().toISOString() },
  { id: 'idx1', name: 'Production Index', status: 'healthy', lastBuilt: new Date().toISOString(), machineId: 'MACHINE-001' },
  { id: 'idx2', name: 'Staging Index', status: 'building', lastBuilt: new Date(Date.now() - 3600000).toISOString(), machineId: 'MACHINE-002' },
];

const STUB_ERROR_KEYS: ErrorKey[] = [
  {
    id: 'ek1',
    key: 'PeriodicIdle:waitComplete',
    normalizedKey: 'periodicidle:waitcomplete',
    occurrenceCount: 42,
    lastIndexed: new Date().toISOString(),
    firstSeen: new Date(Date.now() - 86400000 * 7).toISOString(),
  },
  {
    id: 'ek2',
    key: 'VALVE:timeout',
    normalizedKey: 'valve:timeout',
    occurrenceCount: 18,
    lastIndexed: new Date().toISOString(),
    firstSeen: new Date(Date.now() - 86400000 * 3).toISOString(),
  },
];

function generateStubOccurrences(errorKey: string, count: number): Occurrence[] {
  const occurrences: Occurrence[] = [];
  for (let i = 0; i < count; i++) {
    occurrences.push({
      id: `occ-${errorKey}-${i}`,
      errorKey,
      filePath: `/opt/memjet/src/${errorKey.toLowerCase().replace(':', '_')}.py`,
      lineNumber: 142 + i * 5,
      enclosureName: errorKey.split(':')[0],
      signature: `def ${errorKey.split(':')[1] || 'handler'}(self, timeout=30):`,
      matchedLine: `2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] ${errorKey}`,
      context: `def ${errorKey.split(':')[1] || 'handler'}(self, timeout=30):\n    if not self._event.wait(timeout):`,
      confidence: 0.95 - (i * 0.05),
      timestamp: new Date(Date.now() - i * 3600000).toISOString(),
      metadata: { component: errorKey.split(':')[0], level: 'E' },
    });
  }
  return occurrences.sort((a, b) => b.confidence - a.confidence);
}

export async function getIndexStatus(): Promise<IndexStatus[]> {
  await delay(300);
  return [...STUB_INDEXES];
}

export async function listErrorKeys(filterText?: string): Promise<ErrorKey[]> {
  await delay(400);
  let results = [...STUB_ERROR_KEYS];
  if (filterText) {
    const lower = filterText.toLowerCase();
    results = results.filter(
      (ek) =>
        ek.key.toLowerCase().includes(lower) ||
        ek.normalizedKey.includes(lower)
    );
  }
  return results;
}

export async function searchLibrary(
  queryText: string,
  filters?: SearchFilters,
  targetIndex?: string
): Promise<SearchResult[]> {
  await delay(800);
  
  // Generate stub results grouped by ErrorKey
  const results: SearchResult[] = [
    {
      errorKey: 'PeriodicIdle:waitComplete',
      totalCount: 5,
      occurrences: generateStubOccurrences('PeriodicIdle:waitComplete', 5),
    },
    {
      errorKey: 'VALVE:timeout',
      totalCount: 3,
      occurrences: generateStubOccurrences('VALVE:timeout', 3),
    },
  ];

  return results;
}

export async function liveScan(
  queryText: string,
  filters?: SearchFilters,
  targetIndex?: string
): Promise<SearchResult[]> {
  await delay(1500); // Simulate longer scan
  // Return similar stub data as searchLibrary
  // TODO: Add progress callbacks for live scanning
  return searchLibrary(queryText, filters, targetIndex);
}

export async function getOccurrenceDetail(occurrenceId: string): Promise<OccurrenceDetail> {
  await delay(300);
  
  const [errorKey, index] = occurrenceId.split('-').slice(1);
  const fullErrorKey = errorKey && index ? `${errorKey}:${index}` : 'PeriodicIdle:waitComplete';
  
  return {
    id: occurrenceId,
    errorKey: fullErrorKey,
    filePath: `/opt/memjet/src/${fullErrorKey.toLowerCase().replace(':', '_')}.py`,
    lineNumber: 142,
    enclosureName: fullErrorKey.split(':')[0],
    signature: `def ${fullErrorKey.split(':')[1] || 'waitComplete'}(self, timeout=30):`,
    matchedLine: `2025-12-19T05:22:06.895453+11:00 RS20300529 Kareela0: <E> [#4] ${fullErrorKey}`,
    context: `def ${fullErrorKey.split(':')[1] || 'waitComplete'}(self, timeout=30):\n    if not self._event.wait(timeout):`,
    confidence: 0.95,
    timestamp: new Date().toISOString(),
    metadata: { component: fullErrorKey.split(':')[0], level: 'E' },
    fullCode: `def ${fullErrorKey.split(':')[1] || 'waitComplete'}(self, timeout=30):
    """Wait for the periodic idle event to complete."""
    if not self._event.wait(timeout):
        raise TimeoutError(f"PeriodicIdle waitComplete timed out after {timeout}s")
    return self._status`,
    summary: `Function that waits for a ${fullErrorKey.split(':')[0]} event with a configurable timeout.`,
    relatedOccurrences: [`occ-${errorKey}-1`, `occ-${errorKey}-2`],
  };
}

