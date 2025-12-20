export type UserRole = 'admin' | 'tech' | 'customer';

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
}

export interface IndexStatus {
  id: string;
  name: string;
  status: 'healthy' | 'building' | 'error' | 'unknown';
  lastBuilt?: string;
  machineId?: string;
}

export interface ErrorKey {
  id: string;
  key: string;
  normalizedKey: string;
  occurrenceCount: number;
  lastIndexed: string;
  firstSeen: string;
}

export interface ErrorKeyGroup {
  errorKeyId: string;
  displayKey: string;
  normalizedKey: string;
  count: number;
  occurrences: Occurrence[];
}

export interface Occurrence {
  id: string;
  errorKey: string;
  filePath: string;
  lineNumber: number;
  enclosureName?: string;
  signature?: string;
  matchedLine: string;
  context: string;
  confidence: number;
  timestamp: string;
  metadata?: Record<string, string>;
}

export interface SearchResult {
  errorKey: string;
  occurrences: Occurrence[];
  totalCount: number;
}

export interface SearchFilters {
  minConfidence?: number;
  filePath?: string;
  functionName?: string;
  dateRange?: {
    from: string;
    to: string;
  };
}

export interface OccurrenceDetail extends Occurrence {
  fullCode?: string;
  summary?: string;
  relatedOccurrences?: string[];
}

