'use client';

import { useState, useEffect, useMemo } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import {
  listMachines,
  searchIndex,
  generateAiSummary,
  getCallgraph,
  type Machine,
  type SearchResult,
  type CallgraphResponse,
  type CallgraphNode,
} from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ErrorDebugNav } from '@/components/ErrorDebugNav';

interface SearchResponse {
  machine_id: string;
  query: string;
  parsed?: {
    route: string;
    confidence: number;
    query_text: string;
    payload?: string;
    component?: string;
    severity?: string;
    tag?: string;
  };
  results: SearchResult[];
  total_matches: number;
  debug?: any;
}

interface ContextBundle {
  machineId: string;
  query_raw: string;
  debug: boolean;
  search_response: SearchResponse;
  parsed: SearchResponse['parsed'] | null;
  results: SearchResult[];
  selectedCandidate: SearchResult | null;
  built_at: string;
}

export default function TraceViewPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const machineId = params.machineId as string;
  const [mounted, setMounted] = useState(false);
  const [machine, setMachine] = useState<Machine | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search state
  const [query, setQuery] = useState('');
  const [debug, setDebug] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<SearchResult | null>(null);
  const [evidenceTab, setEvidenceTab] = useState<string>('summary');
  const [contextBundle, setContextBundle] = useState<ContextBundle | null>(null);
  const [showBundle, setShowBundle] = useState(false);
  const [generatingSummary, setGeneratingSummary] = useState(false);

  // Call Explorer state
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
  const [callgraphData, setCallgraphData] = useState<CallgraphResponse | null>(null);
  const [loadingCallgraph, setLoadingCallgraph] = useState(false);
  const [callgraphError, setCallgraphError] = useState<string | null>(null);
  const [callgraphDirection, setCallgraphDirection] = useState<'out' | 'in'>('out');
  const [callgraphDepth, setCallgraphDepth] = useState(1);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [focusedNode, setFocusedNode] = useState<CallgraphNode | null>(null);

  // Load machine and handle URL params
  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const loadMachine = async () => {
      try {
        setLoading(true);
        setError(null);
        const machines = await listMachines();
        const found = machines.find((m) => m.id === machineId);
        if (!found) {
          setError('Machine not found');
          setMachine(null);
          return;
        }
        setMachine(found);
      } catch (err: any) {
        setError(err.message || 'Failed to load machine');
        setMachine(null);
      } finally {
        setLoading(false);
      }
    };

    loadMachine();

    // Handle URL query params
    const urlQuery = searchParams.get('q');
    const urlDebug = searchParams.get('debug') === '1' || searchParams.get('debug') === 'true';
    
    if (urlQuery) {
      setQuery(urlQuery);
      setDebug(urlDebug);
      // Auto-search after a short delay to ensure state is set
      setTimeout(() => {
        handleSearch(urlQuery, urlDebug);
      }, 100);
    }
  }, [machineId, mounted, searchParams]);

  const handleSearch = async (queryText?: string, debugMode?: boolean) => {
    const searchQuery = queryText || query;
    const debugModeValue = debugMode !== undefined ? debugMode : debug;
    
    if (!searchQuery.trim()) {
      console.log('[TRACE_VIEW] Search skipped: empty query');
      return;
    }

    try {
      console.log('[TRACE_VIEW] Starting search', { query: searchQuery, debug: debugModeValue });
      setSearching(true);
      setError(null);
      setSelectedCandidate(null);
      setContextBundle(null);
      setShowBundle(false);

      const response = await searchIndex(machineId, searchQuery, debugModeValue);
      console.log('[TRACE_VIEW] Search completed', {
        resultsCount: response.results.length,
        totalMatches: response.total_matches,
        hasParsed: !!response.parsed,
      });

      const fullResponse: SearchResponse = {
        machine_id: response.machine_id,
        query: response.query,
        parsed: response.parsed,
        results: response.results,
        total_matches: response.total_matches,
        debug: response.debug,
      };

      setSearchResponse(fullResponse);

      // Update URL with query params
      const params = new URLSearchParams();
      params.set('q', searchQuery);
      if (debugModeValue) {
        params.set('debug', '1');
      }
      router.push(`/tech/error-debug/${machineId}/map?${params.toString()}`, { scroll: false });

      // Auto-select first candidate if available
      if (response.results.length > 0) {
        setSelectedCandidate(response.results[0]);
        console.log('[TRACE_VIEW] Auto-selected first candidate', {
          error_key: response.results[0].error_key,
          score: response.results[0].score,
        });
        // Auto-select first chunk for call explorer
        if (response.results[0].chunks.length > 0) {
          const firstChunkId = response.results[0].chunks[0].chunk_id;
          setSelectedChunkId(firstChunkId);
          loadCallgraph(firstChunkId, 'out', 1);
        }
      }
    } catch (err: any) {
      const errorMsg = err.message || 'Search failed';
      setError(errorMsg);
      console.error('[TRACE_VIEW] Search error:', err);
    } finally {
      setSearching(false);
    }
  };

  const handleBuildBundle = () => {
    if (!searchResponse) {
      console.warn('[TRACE_VIEW] Cannot build bundle: no search response');
      return;
    }

    const bundle: ContextBundle = {
      machineId,
      query_raw: query,
      debug,
      search_response: searchResponse,
      parsed: searchResponse.parsed ?? null,
      results: searchResponse.results,
      selectedCandidate: selectedCandidate,
      built_at: new Date().toISOString(),
    };

    setContextBundle(bundle);
    setShowBundle(true);

    console.log('[TRACE_VIEW] Built context bundle', {
      keys: Object.keys(bundle),
      resultsCount: bundle.results.length,
      hasSelectedCandidate: !!bundle.selectedCandidate,
      hasParsed: !!bundle.parsed,
    });
  };

  const loadCallgraph = async (chunkId: string, direction: 'out' | 'in', depth: number) => {
    if (!chunkId) {
      console.warn('[CALL_EXPLORER] Cannot load callgraph: no chunk_id');
      return;
    }

    try {
      console.log('[CALL_EXPLORER] Loading callgraph', { chunkId, direction, depth });
      setLoadingCallgraph(true);
      setCallgraphError(null);

      const response = await getCallgraph(machineId, chunkId, direction, depth, 200);
      console.log('[CALL_EXPLORER] Callgraph loaded', {
        nodesCount: response.nodes.length,
        edgesCount: response.edges.length,
        unresolvedCount: response.unresolved.length,
      });

      setCallgraphData(response);
      setExpandedNodes(new Set([chunkId])); // Auto-expand root
      if (response.nodes.length > 0) {
        setFocusedNode(response.nodes[0]);
      }
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to load callgraph';
      setCallgraphError(errorMsg);
      console.error('[CALL_EXPLORER] Callgraph error:', err);
    } finally {
      setLoadingCallgraph(false);
    }
  };

  const handleNodeClick = (node: CallgraphNode) => {
    console.log('[CALL_EXPLORER] Node clicked', { chunkId: node.chunk_id, label: node.label });
    setFocusedNode(node);
    setSelectedChunkId(node.chunk_id);
    
    // Expand/collapse node
    const newExpanded = new Set(expandedNodes);
    if (newExpanded.has(node.chunk_id)) {
      newExpanded.delete(node.chunk_id);
    } else {
      newExpanded.add(node.chunk_id);
      // Lazy load children if not already loaded
      if (callgraphData && callgraphDepth === 1) {
        // Load depth 2 for this node
        loadCallgraph(node.chunk_id, callgraphDirection, 2);
      }
    }
    setExpandedNodes(newExpanded);
  };

  const handleGenerateSummary = async () => {
    if (!contextBundle || !searchResponse) {
      console.warn('[TRACE_VIEW] Cannot generate summary: no bundle or search response');
      return;
    }

    try {
      console.log('[TRACE_VIEW] Generating AI summary');
      setGeneratingSummary(true);
      
      // Transform contextBundle to ai_summary_v1 format
      const aiSummaryPayload = {
        schema_version: 'ai_summary_v1',
        query: {
          raw: contextBundle.query_raw,
        },
        parsed: contextBundle.parsed,
        results: contextBundle.results,
      };
      
      console.log('[TRACE_VIEW] Sending AI summary payload', {
        schema_version: aiSummaryPayload.schema_version,
        query_raw: aiSummaryPayload.query.raw,
        resultsCount: aiSummaryPayload.results.length,
      });
      
      const response = await generateAiSummary(aiSummaryPayload, debug);
      console.log('[TRACE_VIEW] AI summary generated', {
        ok: response.ok,
        confidence: response.summary.confidence.level,
      });
      // TODO: Show summary in UI (for now just log)
      alert(`Summary generated with ${response.summary.confidence.level} confidence. Check console for details.`);
    } catch (err: any) {
      console.error('[TRACE_VIEW] AI summary error:', err);
      alert(`Failed to generate summary: ${err.message}`);
    } finally {
      setGeneratingSummary(false);
    }
  };

  const user = mounted ? getCurrentUser() : null;

  if (mounted && (!user || !hasRole(user, 'TECHNICIAN'))) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p>This page is only accessible to TECHNICIAN and ADMIN users.</p>
      </div>
    );
  }

  if (!mounted || loading) {
    return (
      <div className="p-8">
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  if (error && !machine) {
    return (
      <div className="p-8">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      </div>
    );
  }

  if (!machine) {
    return (
      <div className="p-8">
        <div className="text-center py-8">Machine not found</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <ErrorDebugNav machineId={machineId} />

      <div className="flex-1 flex flex-col min-h-0 w-full overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b bg-white flex-shrink-0">
          <h1 className="text-2xl font-bold">Trace View</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Query-driven trace from log line to likely source
          </p>
        </div>

        {/* Input Section */}
        <div className="px-6 py-4 border-b bg-white flex-shrink-0">
          <div className="flex gap-3 items-end">
            <div className="flex-1">
              <label className="text-sm font-medium mb-2 block">Log line / Query</label>
              <textarea
                className="w-full border rounded px-3 py-2 text-sm min-h-[80px] font-mono"
                placeholder="Paste log line or enter search query..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    handleSearch();
                  }
                }}
              />
            </div>
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="debug-toggle"
                  checked={debug}
                  onChange={(e) => setDebug(e.target.checked)}
                  className="rounded"
                />
                <label htmlFor="debug-toggle" className="text-sm">
                  Debug
                </label>
              </div>
              <Button
                onClick={() => handleSearch()}
                disabled={searching || !query.trim()}
              >
                {searching ? 'Searching...' : 'Search'}
              </Button>
            </div>
          </div>
        </div>

        {/* Main Content */}
        {error && searchResponse === null && (
          <div className="px-6 py-4">
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          </div>
        )}

        {searchResponse && (
          <div className="flex-1 flex min-h-0 overflow-hidden">
            {/* Left Panel: Parsed Facts */}
            <div className="w-64 border-r bg-muted/30 overflow-y-auto flex-shrink-0">
              <Card className="border-0 rounded-none h-full">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold">Parsed Facts</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {searchResponse.parsed ? (
                    <>
                      <div>
                        <div className="font-medium text-muted-foreground">Route</div>
                        <div className="mt-1">{searchResponse.parsed.route || 'N/A'}</div>
                      </div>
                      <div>
                        <div className="font-medium text-muted-foreground">Confidence</div>
                        <div className="mt-1">
                          {(searchResponse.parsed.confidence * 100).toFixed(1)}%
                        </div>
                      </div>
                      <div>
                        <div className="font-medium text-muted-foreground">Normalized Query</div>
                        <div className="mt-1 font-mono text-xs break-words">
                          {searchResponse.parsed.query_text || 'N/A'}
                        </div>
                      </div>
                      {searchResponse.parsed.component && (
                        <div>
                          <div className="font-medium text-muted-foreground">Component</div>
                          <div className="mt-1">{searchResponse.parsed.component}</div>
                        </div>
                      )}
                      {searchResponse.parsed.severity && (
                        <div>
                          <div className="font-medium text-muted-foreground">Severity</div>
                          <div className="mt-1">{searchResponse.parsed.severity}</div>
                        </div>
                      )}
                      {searchResponse.parsed.tag && (
                        <div>
                          <div className="font-medium text-muted-foreground">Tag</div>
                          <div className="mt-1">{searchResponse.parsed.tag}</div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-muted-foreground">No parsed data available</div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Middle Panel: Candidates */}
            <div className="w-80 border-r bg-white overflow-y-auto flex-shrink-0">
              <Card className="border-0 rounded-none h-full">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold">
                    Candidates ({searchResponse.results.length})
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {searchResponse.results.length === 0 ? (
                    <div className="p-4 text-sm text-muted-foreground">No candidates found</div>
                  ) : (
                    <div className="divide-y">
                      {searchResponse.results.map((result, index) => (
                        <button
                          key={result.error_key}
                          onClick={() => {
                            setSelectedCandidate(result);
                            console.log('[TRACE_VIEW] Selected candidate', {
                              error_key: result.error_key,
                              score: result.score,
                              match_type: result.match_type,
                            });
                            // Select first chunk for call explorer
                            if (result.chunks.length > 0) {
                              const firstChunkId = result.chunks[0].chunk_id;
                              setSelectedChunkId(firstChunkId);
                              loadCallgraph(firstChunkId, callgraphDirection, callgraphDepth);
                            }
                          }}
                          className={`w-full text-left p-4 hover:bg-muted/50 transition-colors ${
                            selectedCandidate?.error_key === result.error_key
                              ? 'bg-muted border-l-4 border-l-primary'
                              : ''
                          }`}
                        >
                          <div className="flex items-start justify-between mb-2">
                            <span className="text-xs font-medium text-muted-foreground">
                              #{index + 1}
                            </span>
                            <span className="text-xs font-medium">
                              {result.match_type} • {result.score.toFixed(2)}
                            </span>
                          </div>
                          <div className="font-medium text-sm mb-1">{result.error_key}</div>
                          {result.chunks.length > 0 && (
                            <div className="text-xs text-muted-foreground">
                              {result.chunks[0].file_path}
                              {result.chunks[0].function_name && (
                                <> • {result.chunks[0].function_name}</>
                              )}
                            </div>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* Right Panel: Evidence Viewer */}
            <div className="flex-1 bg-white overflow-y-auto">
              {selectedCandidate ? (
                <Card className="border-0 rounded-none h-full">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-semibold">Evidence</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <Tabs value={evidenceTab} onValueChange={setEvidenceTab}>
                      <TabsList className="grid w-full grid-cols-4">
                        <TabsTrigger value="summary">Summary</TabsTrigger>
                        <TabsTrigger value="code">Code</TabsTrigger>
                        <TabsTrigger value="metadata">Metadata</TabsTrigger>
                        <TabsTrigger value="raw">Raw</TabsTrigger>
                      </TabsList>

                      <TabsContent value="summary" className="mt-4">
                        <div className="space-y-4">
                          <div>
                            <div className="font-medium mb-2">Candidate</div>
                            <div className="text-sm">
                              <div className="font-mono">{selectedCandidate.error_key}</div>
                              <div className="text-muted-foreground mt-1">
                                Match: {selectedCandidate.match_type} • Score: {selectedCandidate.score.toFixed(2)}
                              </div>
                            </div>
                          </div>
                          {selectedCandidate.chunks.length > 0 && (
                            <div>
                              <div className="font-medium mb-2">Top Snippets</div>
                              <div className="space-y-2">
                                {selectedCandidate.chunks.slice(0, 3).map((chunk, idx) => (
                                  <div key={chunk.chunk_id} className="text-sm border rounded p-3">
                                    <div className="font-mono text-xs mb-1">
                                      {chunk.file_path}:{chunk.line_start}-{chunk.line_end}
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                      {chunk.function_name}
                                      {chunk.class_name && ` (${chunk.class_name})`}
                                    </div>
                                    {chunk.leading_comment && (
                                      <div className="mt-2 text-xs italic text-muted-foreground">
                                        {chunk.leading_comment}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </TabsContent>

                      <TabsContent value="code" className="mt-4">
                        {selectedCandidate.chunks.length > 0 ? (
                          <div className="space-y-4">
                            {selectedCandidate.chunks.map((chunk) => (
                              <div key={chunk.chunk_id} className="border rounded">
                                <div className="bg-muted px-3 py-2 text-xs font-medium">
                                  {chunk.file_path}:{chunk.line_start}-{chunk.line_end}
                                </div>
                                <div className="p-4">
                                  {chunk.signature && (
                                    <div className="mb-3">
                                      <div className="text-xs font-medium text-muted-foreground mb-1">
                                        Signature
                                      </div>
                                      <pre className="text-xs font-mono bg-muted p-2 rounded overflow-x-auto">
                                        {chunk.signature}
                                      </pre>
                                    </div>
                                  )}
                                  {chunk.docstring && (
                                    <div className="mb-3">
                                      <div className="text-xs font-medium text-muted-foreground mb-1">
                                        Docstring
                                      </div>
                                      <div className="text-xs italic text-muted-foreground">
                                        {chunk.docstring}
                                      </div>
                                    </div>
                                  )}
                                  {chunk.leading_comment && (
                                    <div className="mb-3">
                                      <div className="text-xs font-medium text-muted-foreground mb-1">
                                        Leading Comment
                                      </div>
                                      <div className="text-xs text-muted-foreground">
                                        {chunk.leading_comment}
                                      </div>
                                    </div>
                                  )}
                                  <div>
                                    <div className="text-xs font-medium text-muted-foreground mb-1">
                                      Code
                                    </div>
                                    <pre className="text-xs font-mono bg-muted p-3 rounded overflow-x-auto">
                                      {chunk.code}
                                    </pre>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-sm text-muted-foreground">No code chunks available</div>
                        )}
                      </TabsContent>

                      <TabsContent value="metadata" className="mt-4">
                        <div className="space-y-3 text-sm">
                          <div>
                            <div className="font-medium text-muted-foreground mb-1">Error Key</div>
                            <div className="font-mono">{selectedCandidate.error_key}</div>
                          </div>
                          <div>
                            <div className="font-medium text-muted-foreground mb-1">Match Type</div>
                            <div>{selectedCandidate.match_type}</div>
                          </div>
                          <div>
                            <div className="font-medium text-muted-foreground mb-1">Score</div>
                            <div>{selectedCandidate.score.toFixed(4)}</div>
                          </div>
                          {selectedCandidate.chunks.length > 0 && (
                            <div>
                              <div className="font-medium text-muted-foreground mb-2">Chunks</div>
                              <div className="space-y-2">
                                {selectedCandidate.chunks.map((chunk) => (
                                  <div key={chunk.chunk_id} className="border rounded p-3">
                                    <div className="font-mono text-xs mb-2">
                                      {chunk.file_path}
                                    </div>
                                    <div className="grid grid-cols-2 gap-2 text-xs">
                                      <div>
                                        <span className="text-muted-foreground">Function:</span>{' '}
                                        {chunk.function_name || 'N/A'}
                                      </div>
                                      {chunk.class_name && (
                                        <div>
                                          <span className="text-muted-foreground">Class:</span>{' '}
                                          {chunk.class_name}
                                        </div>
                                      )}
                                      <div>
                                        <span className="text-muted-foreground">Lines:</span>{' '}
                                        {chunk.line_start}-{chunk.line_end}
                                      </div>
                                      <div>
                                        <span className="text-muted-foreground">Chunk ID:</span>{' '}
                                        {chunk.chunk_id}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </TabsContent>

                      <TabsContent value="raw" className="mt-4">
                        <pre className="text-xs font-mono bg-muted p-4 rounded overflow-x-auto">
                          {JSON.stringify(selectedCandidate, null, 2)}
                        </pre>
                      </TabsContent>
                    </Tabs>
                  </CardContent>
                </Card>
              ) : (
                <div className="p-8 text-center text-muted-foreground">
                  Select a candidate to view evidence
                </div>
              )}
            </div>
          </div>
        )}

        {/* Call Explorer */}
        {searchResponse && selectedChunkId && (
          <div className="border-t bg-white flex-shrink-0 flex flex-col" style={{ height: '400px' }}>
            <div className="px-6 py-3 border-b flex items-center justify-between">
              <div className="flex items-center gap-4">
                <h3 className="text-sm font-semibold">Call Explorer</h3>
                <div className="flex items-center gap-2">
                  <select
                    value={callgraphDirection}
                    onChange={(e) => {
                      const dir = e.target.value as 'out' | 'in';
                      setCallgraphDirection(dir);
                      if (selectedChunkId) {
                        loadCallgraph(selectedChunkId, dir, callgraphDepth);
                      }
                    }}
                    className="text-xs border rounded px-2 py-1"
                  >
                    <option value="out">Calls</option>
                    <option value="in">Called By</option>
                  </select>
                  <select
                    value={callgraphDepth}
                    onChange={(e) => {
                      const depth = parseInt(e.target.value);
                      setCallgraphDepth(depth);
                      if (selectedChunkId) {
                        loadCallgraph(selectedChunkId, callgraphDirection, depth);
                      }
                    }}
                    className="text-xs border rounded px-2 py-1"
                  >
                    <option value="1">Depth 1</option>
                    <option value="2">Depth 2</option>
                    <option value="3">Depth 3</option>
                  </select>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      if (selectedChunkId) {
                        loadCallgraph(selectedChunkId, callgraphDirection, callgraphDepth);
                      }
                    }}
                    disabled={loadingCallgraph}
                  >
                    Refresh
                  </Button>
                </div>
              </div>
            </div>
            <div className="flex-1 flex min-h-0 overflow-hidden">
              {/* Left: Tree View */}
              <div className="w-1/2 border-r overflow-y-auto p-4">
                {loadingCallgraph ? (
                  <div className="text-sm text-muted-foreground">Loading callgraph...</div>
                ) : callgraphError ? (
                  <div className="text-sm text-red-600">{callgraphError}</div>
                ) : callgraphData ? (
                  <div className="space-y-1">
                    {callgraphData.warning && (
                      <div className="text-xs text-yellow-600 mb-2">{callgraphData.warning}</div>
                    )}
                    {callgraphData.nodes.map((node) => {
                      const isRoot = node.chunk_id === selectedChunkId;
                      const isExpanded = expandedNodes.has(node.chunk_id);
                      const hasChildren = callgraphData.edges.some(
                        (e) => callgraphDirection === 'out' ? e.from === node.chunk_id : e.to === node.chunk_id
                      );
                      const isFocused = focusedNode?.chunk_id === node.chunk_id;

                      return (
                        <div
                          key={node.chunk_id}
                          className={`text-xs cursor-pointer p-2 rounded hover:bg-muted/50 ${
                            isFocused ? 'bg-muted border-l-2 border-l-primary' : ''
                          } ${isRoot ? 'font-semibold' : ''}`}
                          onClick={() => handleNodeClick(node)}
                          style={{ marginLeft: isRoot ? '0' : '1rem' }}
                        >
                          <div className="flex items-center gap-2">
                            {hasChildren && (
                              <span className="text-muted-foreground">
                                {isExpanded ? '▼' : '▶'}
                              </span>
                            )}
                            <span className="truncate">{node.label}</span>
                          </div>
                        </div>
                      );
                    })}
                    {callgraphData.unresolved.length > 0 && (
                      <div className="mt-4 pt-4 border-t">
                        <div className="text-xs font-medium text-muted-foreground mb-2">
                          Unresolved Calls
                        </div>
                        {callgraphData.unresolved.map((raw, idx) => (
                          <div key={idx} className="text-xs text-muted-foreground font-mono p-1">
                            {raw}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">No callgraph data</div>
                )}
              </div>

              {/* Right: Focused Function Details */}
              <div className="w-1/2 overflow-y-auto">
                {focusedNode ? (
                  <Card className="border-0 rounded-none h-full">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Focused Function</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3 text-sm">
                        <div>
                          <div className="font-medium text-muted-foreground mb-1">Function</div>
                          <div className="font-mono">{focusedNode.function_name}</div>
                        </div>
                        {focusedNode.class_name && (
                          <div>
                            <div className="font-medium text-muted-foreground mb-1">Class</div>
                            <div>{focusedNode.class_name}</div>
                          </div>
                        )}
                        <div>
                          <div className="font-medium text-muted-foreground mb-1">File</div>
                          <div className="font-mono text-xs">{focusedNode.file_path}</div>
                        </div>
                        <div>
                          <div className="font-medium text-muted-foreground mb-1">Route</div>
                          <div>{focusedNode.route}</div>
                        </div>
                        <div>
                          <div className="font-medium text-muted-foreground mb-1">Chunk ID</div>
                          <div className="font-mono text-xs">{focusedNode.chunk_id}</div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="p-8 text-center text-muted-foreground text-sm">
                    Click a node to view details
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        {searchResponse && (
          <div className="border-t bg-white px-6 py-4 flex-shrink-0 flex justify-center gap-3">
            <Button onClick={handleBuildBundle} disabled={!searchResponse}>
              Build Context Bundle
            </Button>
            <Button
              onClick={handleGenerateSummary}
              disabled={!contextBundle || generatingSummary}
              variant="outline"
            >
              {generatingSummary ? 'Generating...' : 'Generate AI Summary'}
            </Button>
          </div>
        )}

        {/* Context Bundle JSON Viewer */}
        {showBundle && contextBundle && (
          <div className="border-t bg-white px-6 py-4 flex-shrink-0 max-h-96 overflow-hidden flex flex-col">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium">Context Bundle (Raw JSON)</div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowBundle(false)}
              >
                Hide
              </Button>
            </div>
            <div className="flex-1 overflow-auto border rounded bg-muted/30">
              <pre className="text-xs font-mono p-4">
                {JSON.stringify(contextBundle, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
