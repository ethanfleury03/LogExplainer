'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import {
  listMachines,
  searchIndex,
  generateAiSummary,
  getCallgraph,
  getChunksByIds,
  type Machine,
  type SearchResult,
  type CallgraphResponse,
  type CallgraphNode,
  type ChunkDetail,
} from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

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
  calledFunctions?: ChunkDetail[];
  built_at: string;
}

export default function CallTracePage() {
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
  const [contextBundle, setContextBundle] = useState<ContextBundle | null>(null);
  const [generatingSummary, setGeneratingSummary] = useState(false);
  const [buildingBundle, setBuildingBundle] = useState(false);
  const [aiSummary, setAiSummary] = useState<any | null>(null);

  // Call Explorer state - Tree structure
  interface TreeNodeState {
    chunkId: string;
    label: string;
    filePath?: string;
    functionName?: string;
    className?: string;
    route?: string;
    childrenIds: string[] | null;
    isExpanded: boolean;
    isLoading: boolean;
    unresolved?: string[];
  }

  const [rootChunkId, setRootChunkId] = useState<string | null>(null);
  const [nodeStateById, setNodeStateById] = useState<Record<string, TreeNodeState>>({});
  const [edgesByParent, setEdgesByParent] = useState<Record<string, string[]>>({});
  const [callgraphDirection, setCallgraphDirection] = useState<'out' | 'in'>('out');
  const [loadingCallgraph, setLoadingCallgraph] = useState(false);
  const [callgraphError, setCallgraphError] = useState<string | null>(null);
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
      setTimeout(() => {
        handleSearch(urlQuery, urlDebug);
      }, 100);
    }
  }, [machineId, mounted, searchParams]);

  const handleSearch = async (queryText?: string, debugMode?: boolean) => {
    const searchQuery = queryText || query;
    const debugModeValue = debugMode !== undefined ? debugMode : debug;
    
    if (!searchQuery.trim()) {
      console.log('[CALL_TRACE] Search skipped: empty query');
      return;
    }

    try {
      console.log('[CALL_TRACE] Starting search', { query: searchQuery, debug: debugModeValue });
      setSearching(true);
      setError(null);
      setSelectedCandidate(null);
      setContextBundle(null);
      setAiSummary(null);

      const response = await searchIndex(machineId, searchQuery, debugModeValue);
      console.log('[CALL_TRACE] Search completed', {
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
      router.push(`/tech/call-trace/${machineId}?${params.toString()}`, { scroll: false });

      // Auto-select first candidate if available
      if (response.results.length > 0) {
        setSelectedCandidate(response.results[0]);
        console.log('[CALL_TRACE] Auto-selected first candidate', {
          error_key: response.results[0].error_key,
          score: response.results[0].score,
        });
        // Auto-select first chunk for call explorer
        if (response.results[0].chunks.length > 0) {
          const firstChunk = response.results[0].chunks[0];
          const firstChunkId = firstChunk.chunk_id;
          setRootChunkId(firstChunkId);
          initializeTreeNode(firstChunkId, firstChunk);
          loadNodeChildren(firstChunkId, 'out');
        }
      }
    } catch (err: any) {
      const errorMsg = err.message || 'Search failed';
      setError(errorMsg);
      console.error('[CALL_TRACE] Search error:', err);
    } finally {
      setSearching(false);
    }
  };

  const handleBuildBundle = async () => {
    if (!searchResponse) {
      console.warn('[CALL_TRACE] Cannot build bundle: no search response');
      return;
    }

    console.log('[CALL_TRACE] Building context bundle...');
    setBuildingBundle(true);
    
    let calledFunctions: ChunkDetail[] = [];
    
    if (selectedCandidate && selectedCandidate.chunks.length > 0) {
      const selectedChunk = selectedCandidate.chunks[0];
      const selectedChunkId = selectedChunk.chunk_id;
      
      console.log('[CALL_TRACE] Fetching called functions for chunk:', selectedChunkId);
      
      try {
        const callgraphResponse = await getCallgraph(machineId, selectedChunkId, 'out', 3, 500);
        
        const calleeIds = new Set<string>();
        callgraphResponse.edges
          .filter((e) => e.from === selectedChunkId)
          .forEach((e) => calleeIds.add(e.to));
        
        if (selectedChunk.calls && Array.isArray(selectedChunk.calls)) {
          selectedChunk.calls.forEach((call: any) => {
            if (call.resolved_chunk_id) {
              calleeIds.add(call.resolved_chunk_id);
            }
          });
        }
        
        const visited = new Set<string>([selectedChunkId]);
        const queue: Array<{ chunkId: string; depth: number }> = Array.from(calleeIds).map(id => ({ chunkId: id, depth: 1 }));
        
        while (queue.length > 0 && visited.size < 100) {
          const { chunkId, depth } = queue.shift()!;
          if (visited.has(chunkId) || depth >= 3) continue;
          visited.add(chunkId);
          
          try {
            const childCallgraph = await getCallgraph(machineId, chunkId, 'out', 1, 200);
            childCallgraph.edges
              .filter((e) => e.from === chunkId)
              .forEach((e) => {
                if (!visited.has(e.to)) {
                  calleeIds.add(e.to);
                  queue.push({ chunkId: e.to, depth: depth + 1 });
                }
              });
          } catch (err) {
            console.warn('[CALL_TRACE] Failed to fetch callgraph for chunk:', chunkId, err);
          }
        }
        
        const allCalleeIds = Array.from(calleeIds);
        console.log('[CALL_TRACE] Found', allCalleeIds.length, 'called functions to fetch');
        
        if (allCalleeIds.length > 0) {
          const batchSize = 100;
          for (let i = 0; i < allCalleeIds.length; i += batchSize) {
            const batch = allCalleeIds.slice(i, i + batchSize);
            const chunksResponse = await getChunksByIds(machineId, batch);
            calledFunctions.push(...chunksResponse.chunks);
            
            if (chunksResponse.missing_ids.length > 0) {
              console.warn('[CALL_TRACE] Missing chunks:', chunksResponse.missing_ids);
            }
          }
        }
        
        console.log('[CALL_TRACE] Fetched', calledFunctions.length, 'called function chunks');
      } catch (err: any) {
        console.error('[CALL_TRACE] Error fetching called functions:', err);
      }
    }

    const bundle: ContextBundle = {
      machineId,
      query_raw: query,
      debug,
      search_response: searchResponse,
      parsed: searchResponse.parsed ?? null,
      results: searchResponse.results,
      selectedCandidate: selectedCandidate,
      calledFunctions: calledFunctions.length > 0 ? calledFunctions : undefined,
      built_at: new Date().toISOString(),
    };

    setContextBundle(bundle);

    console.log('[CALL_TRACE] Built context bundle', {
      keys: Object.keys(bundle),
      resultsCount: bundle.results.length,
      hasSelectedCandidate: !!bundle.selectedCandidate,
      hasParsed: !!bundle.parsed,
      calledFunctionsCount: bundle.calledFunctions?.length || 0,
    });
    
    setBuildingBundle(false);
  };

  const initializeTreeNode = (chunkId: string, chunk: any) => {
    const label = chunk.function_name || chunk.chunk_id;
    setNodeStateById((prev) => ({
      ...prev,
      [chunkId]: {
        chunkId,
        label,
        filePath: chunk.file_path,
        functionName: chunk.function_name,
        className: chunk.class_name,
        route: chunk.route || 'unknown',
        childrenIds: null,
        isExpanded: true,
        isLoading: false,
        unresolved: [],
      },
    }));
    setFocusedNode({
      chunk_id: chunkId,
      label,
      file_path: chunk.file_path || '',
      function_name: chunk.function_name || '',
      class_name: chunk.class_name,
      route: chunk.route || 'unknown',
    });
  };

  const loadNodeChildren = async (chunkId: string, direction: 'out' | 'in') => {
    if (!chunkId) {
      console.warn('[CALL_EXPLORER] Cannot load children: no chunk_id');
      return;
    }

    const nodeState = nodeStateById[chunkId];
    if (nodeState && nodeState.childrenIds !== null) {
      setNodeStateById((prev) => ({
        ...prev,
        [chunkId]: { ...prev[chunkId], isExpanded: true },
      }));
      return;
    }

    try {
      console.log('[CALL_EXPLORER] Loading children', { chunkId, direction });
      setNodeStateById((prev) => ({
        ...prev,
        [chunkId]: { ...prev[chunkId], isLoading: true },
      }));
      setCallgraphError(null);

      const response = await getCallgraph(machineId, chunkId, direction, 1, 500);
      console.log('[CALL_EXPLORER] expand node=', chunkId, 'children=', response.nodes.length, 'unresolved=', response.unresolved.length);

      const childrenIds: string[] = [];
      if (direction === 'out') {
        response.edges
          .filter((e) => e.from === chunkId)
          .forEach((e) => {
            if (!childrenIds.includes(e.to)) {
              childrenIds.push(e.to);
            }
          });
      } else {
        response.edges
          .filter((e) => e.to === chunkId)
          .forEach((e) => {
            if (!childrenIds.includes(e.from)) {
              childrenIds.push(e.from);
            }
          });
      }

      setEdgesByParent((prev) => ({
        ...prev,
        [chunkId]: childrenIds,
      }));

      const updatedNodes = { ...nodeStateById };
      response.nodes.forEach((node) => {
        if (!updatedNodes[node.chunk_id]) {
          updatedNodes[node.chunk_id] = {
            chunkId: node.chunk_id,
            label: node.function_name || node.chunk_id,
            filePath: node.file_path,
            functionName: node.function_name,
            className: node.class_name,
            route: node.route,
            childrenIds: null,
            isExpanded: false,
            isLoading: false,
            unresolved: [],
          };
        }
      });

      updatedNodes[chunkId] = {
        ...updatedNodes[chunkId],
        childrenIds,
        isExpanded: true,
        isLoading: false,
        unresolved: response.unresolved || [],
      };

      setNodeStateById(updatedNodes);
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to load children';
      setCallgraphError(errorMsg);
      console.error('[CALL_EXPLORER] Load children error:', err);
      setNodeStateById((prev) => ({
        ...prev,
        [chunkId]: { ...prev[chunkId], isLoading: false, childrenIds: [] },
      }));
    }
  };

  const toggleNodeExpand = (chunkId: string) => {
    const nodeState = nodeStateById[chunkId];
    if (!nodeState) return;

    if (nodeState.isExpanded) {
      setNodeStateById((prev) => ({
        ...prev,
        [chunkId]: { ...prev[chunkId], isExpanded: false },
      }));
      console.log('[CALL_EXPLORER] collapse node=', chunkId);
    } else {
      if (nodeState.childrenIds === null) {
        loadNodeChildren(chunkId, callgraphDirection);
      } else {
        setNodeStateById((prev) => ({
          ...prev,
          [chunkId]: { ...prev[chunkId], isExpanded: true },
        }));
        console.log('[CALL_EXPLORER] expand node=', chunkId, '(already loaded)');
      }
    }
  };

  const TreeNodeRow = ({
    chunkId,
    depth,
    pathSet,
  }: {
    chunkId: string;
    depth: number;
    pathSet: Set<string>;
  }) => {
    const nodeState = nodeStateById[chunkId];
    if (!nodeState) return null;

    const isInPath = pathSet.has(chunkId);
    const isRoot = chunkId === rootChunkId;
    const hasChildren = nodeState.childrenIds !== null && nodeState.childrenIds.length > 0;
    const isExpandable = nodeState.childrenIds === null || hasChildren;
    const isFocused = focusedNode?.chunk_id === chunkId;
    const unresolvedCount = nodeState.unresolved?.length || 0;

    const newPathSet = new Set(pathSet);
    if (!isRoot) {
      newPathSet.add(chunkId);
    }

    const indent = depth * 16;

    return (
      <>
        <div
          className={`text-xs cursor-pointer p-2 rounded hover:bg-muted/50 transition-colors ${
            isFocused ? 'bg-muted border-l-2 border-l-primary' : ''
          } ${isRoot ? 'font-semibold' : ''}`}
          onClick={() => {
            setFocusedNode({
              chunk_id: chunkId,
              label: nodeState.label,
              file_path: nodeState.filePath || '',
              function_name: nodeState.functionName || '',
              class_name: nodeState.className,
              route: nodeState.route || 'unknown',
            });
          }}
          style={{ marginLeft: `${indent}px` }}
        >
          <div className="flex items-center gap-2">
            {isExpandable && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleNodeExpand(chunkId);
                }}
                className="text-muted-foreground hover:text-foreground w-4 h-4 flex items-center justify-center"
                disabled={nodeState.isLoading}
              >
                {nodeState.isLoading ? (
                  <span className="text-xs">⟳</span>
                ) : nodeState.isExpanded ? (
                  '▼'
                ) : (
                  '▶'
                )}
              </button>
            )}
            {!isExpandable && <span className="w-4" />}
            <span className="font-mono truncate flex-1">{nodeState.label}</span>
            {nodeState.filePath && (
              <span className="text-muted-foreground text-xs truncate max-w-[200px]">
                {nodeState.filePath}
              </span>
            )}
            {unresolvedCount > 0 && (
              <span className="text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded">
                {unresolvedCount} unresolved
              </span>
            )}
            {isInPath && !isRoot && (
              <span className="text-xs bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded">
                ↩︎ seen
              </span>
            )}
            {isInPath && nodeState.isExpanded && (
              <span className="text-xs bg-red-100 text-red-800 px-1.5 py-0.5 rounded">
                cycle
              </span>
            )}
          </div>
        </div>
        {nodeState.isExpanded && !isInPath && hasChildren && (
          <div className="border-l border-muted ml-2">
            {nodeState.childrenIds!.map((childId) => (
              <TreeNodeRow
                key={childId}
                chunkId={childId}
                depth={depth + 1}
                pathSet={newPathSet}
              />
            ))}
          </div>
        )}
        {isInPath && nodeState.isExpanded && (
          <div className="text-xs text-muted-foreground p-2" style={{ marginLeft: `${indent + 16}px` }}>
            (cycle detected - not expanding further)
          </div>
        )}
      </>
    );
  };

  const handleGenerateSummary = async () => {
    if (!contextBundle || !searchResponse) {
      console.warn('[CALL_TRACE] Cannot generate summary: no bundle or search response');
      return;
    }

    try {
      console.log('[CALL_TRACE] Generating AI summary');
      setGeneratingSummary(true);
      
      let enhancedResults = [...contextBundle.results];
      
      if (contextBundle.calledFunctions && contextBundle.calledFunctions.length > 0) {
        const calledFunctionsResult: SearchResult = {
          error_key: '__called_functions__',
          chunks: contextBundle.calledFunctions.map((cf) => ({
            chunk_id: cf.chunk_id,
            function_name: cf.function_name,
            class_name: cf.class_name,
            file_path: cf.file_path,
            line_start: cf.line_start,
            line_end: cf.line_end,
            signature: cf.signature,
            code: cf.code,
            docstring: cf.docstring,
            leading_comment: cf.leading_comment,
            error_messages: cf.error_messages,
            log_levels: cf.log_levels,
          })),
          match_type: 'partial',
          score: 0.0,
        };
        
        enhancedResults = [...enhancedResults, calledFunctionsResult];
      }
      
      const aiSummaryPayload = {
        schema_version: 'ai_summary_v1',
        query: {
          raw: contextBundle.query_raw,
        },
        parsed: contextBundle.parsed,
        results: enhancedResults,
      };
      
      console.log('[CALL_TRACE] Sending AI summary payload', {
        schema_version: aiSummaryPayload.schema_version,
        query_raw: aiSummaryPayload.query.raw,
        resultsCount: aiSummaryPayload.results.length,
      });
      
      const response = await generateAiSummary(aiSummaryPayload, debug);
      console.log('[CALL_TRACE] AI summary generated', {
        ok: response.ok,
        confidence: response.summary.confidence.level,
      });
      
      setAiSummary(response.summary);
    } catch (err: any) {
      console.error('[CALL_TRACE] AI summary error:', err);
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
      <div className="flex-1 flex flex-col min-h-0 w-full overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b bg-white flex-shrink-0">
          <h1 className="text-2xl font-bold">Call Trace</h1>
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
                            console.log('[CALL_TRACE] Selected candidate', {
                              error_key: result.error_key,
                              score: result.score,
                              match_type: result.match_type,
                            });
                            if (result.chunks.length > 0) {
                              const firstChunk = result.chunks[0];
                              const firstChunkId = firstChunk.chunk_id;
                              setRootChunkId(firstChunkId);
                              initializeTreeNode(firstChunkId, firstChunk);
                              loadNodeChildren(firstChunkId, callgraphDirection);
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

            {/* Right Panel: Call Explorer */}
            <div className="flex-1 bg-white overflow-y-auto">
              {searchResponse && rootChunkId ? (
                <div className="h-full flex flex-col">
                  <div className="px-6 py-3 border-b flex items-center justify-between flex-shrink-0">
                    <div className="flex items-center gap-4">
                      <h3 className="text-sm font-semibold">Call Explorer</h3>
                      <div className="flex items-center gap-2">
                        <select
                          value={callgraphDirection}
                          onChange={(e) => {
                            const dir = e.target.value as 'out' | 'in';
                            setCallgraphDirection(dir);
                            setEdgesByParent({});
                            setNodeStateById((prev) => {
                              const updated = { ...prev };
                              Object.keys(updated).forEach((id) => {
                                updated[id] = {
                                  ...updated[id],
                                  childrenIds: null,
                                  isExpanded: false,
                                };
                              });
                              return updated;
                            });
                            if (rootChunkId) {
                              loadNodeChildren(rootChunkId, dir);
                            }
                          }}
                          className="text-xs border rounded px-2 py-1"
                        >
                          <option value="out">Calls</option>
                          <option value="in">Called By</option>
                        </select>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setEdgesByParent({});
                            setNodeStateById((prev) => {
                              const updated = { ...prev };
                              Object.keys(updated).forEach((id) => {
                                updated[id] = {
                                  ...updated[id],
                                  childrenIds: null,
                                  isExpanded: false,
                                };
                              });
                              return updated;
                            });
                            if (rootChunkId) {
                              loadNodeChildren(rootChunkId, callgraphDirection);
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
                      {callgraphError ? (
                        <div className="text-sm text-red-600">{callgraphError}</div>
                      ) : rootChunkId && nodeStateById[rootChunkId] ? (
                        <div className="space-y-0">
                          <TreeNodeRow chunkId={rootChunkId} depth={0} pathSet={new Set()} />
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
                                <div className="font-mono">{focusedNode.function_name || focusedNode.chunk_id}</div>
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
                              {nodeStateById[focusedNode.chunk_id]?.unresolved &&
                                nodeStateById[focusedNode.chunk_id].unresolved!.length > 0 && (
                                  <div>
                                    <div className="font-medium text-muted-foreground mb-1">
                                      Unresolved Calls ({nodeStateById[focusedNode.chunk_id].unresolved!.length})
                                    </div>
                                    <div className="space-y-1">
                                      {nodeStateById[focusedNode.chunk_id].unresolved!.map((raw, idx) => (
                                        <div key={idx} className="text-xs text-muted-foreground font-mono p-1 bg-muted rounded">
                                          {raw}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
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
              ) : (
                <div className="p-8 text-center text-muted-foreground">
                  Select a candidate to view call graph
                </div>
              )}
            </div>
          </div>
        )}

        {/* Action Buttons */}
        {searchResponse && (
          <div className="border-t bg-white px-6 py-4 flex-shrink-0 flex justify-center gap-3">
            <Button onClick={handleBuildBundle} disabled={!searchResponse || loadingCallgraph || buildingBundle}>
              {buildingBundle ? 'Building Bundle...' : 'Build Context Bundle'}
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

        {/* AI Summary Display */}
        {aiSummary && (
          <div className="border-t bg-white px-6 py-4 flex-shrink-0">
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">AI Summary</h3>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-1 rounded ${
                    aiSummary.confidence?.level === 'high' ? 'bg-green-100 text-green-800' :
                    aiSummary.confidence?.level === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    {aiSummary.confidence?.level?.toUpperCase() || 'UNKNOWN'} Confidence
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setAiSummary(null)}
                  >
                    Dismiss
                  </Button>
                </div>
              </div>

              <div className="space-y-4">
                {aiSummary.what_it_means && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">What It Means</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm">{aiSummary.what_it_means}</p>
                    </CardContent>
                  </Card>
                )}

                {aiSummary.most_likely_cause && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Most Likely Cause</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm">{aiSummary.most_likely_cause}</p>
                    </CardContent>
                  </Card>
                )}

                {aiSummary.what_to_check && Array.isArray(aiSummary.what_to_check) && aiSummary.what_to_check.length > 0 && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">What To Check</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ol className="list-decimal list-inside space-y-2 text-sm">
                        {aiSummary.what_to_check.map((item: string, idx: number) => (
                          <li key={idx}>{item}</li>
                        ))}
                      </ol>
                    </CardContent>
                  </Card>
                )}

                {aiSummary.where_in_code && Array.isArray(aiSummary.where_in_code) && aiSummary.where_in_code.length > 0 && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Where In Code</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {aiSummary.where_in_code.map((location: any, idx: number) => (
                          <div key={idx} className="border rounded p-3 text-sm">
                            <div className="font-mono text-xs mb-1">
                              {location.file_path}
                              {location.lines && ` (lines ${location.lines})`}
                            </div>
                            {location.symbol && (
                              <div className="font-medium mb-1">{location.symbol}</div>
                            )}
                            {location.why && (
                              <div className="text-muted-foreground">{location.why}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {aiSummary.confidence?.why && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold">Confidence Assessment</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-muted-foreground">{aiSummary.confidence.why}</p>
                    </CardContent>
                  </Card>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

