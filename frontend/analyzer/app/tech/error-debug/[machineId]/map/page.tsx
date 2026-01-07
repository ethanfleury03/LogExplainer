'use client';

import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import { listMachines, type Machine } from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorDebugNav } from '@/components/ErrorDebugNav';
import { CallGraph3D, type CallGraph3DRef } from '@/components/ErrorDebugMap/CallGraph3D';
import { generateDummyCallGraph, type GraphNode, type GraphLink } from '@/components/ErrorDebugMap/dummyCallGraph';
import { GraphErrorBoundary } from '@/components/ErrorDebugMap/GraphErrorBoundary';

export default function MapPage() {
  const params = useParams();
  const router = useRouter();
  const machineId = params.machineId as string;
  const [mounted, setMounted] = useState(false);
  const [machine, setMachine] = useState<Machine | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Graph state
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphLink[] } | null>(null);
  const [highlightQuery, setHighlightQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [showLabels, setShowLabels] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const graphRef = useRef<CallGraph3DRef>(null);

  // Generate initial graph data
  useEffect(() => {
    if (mounted) {
      try {
        const data = generateDummyCallGraph();
        setGraphData(data);
        setGraphError(null);
      } catch (err: any) {
        setGraphError(err.message || 'Failed to generate graph');
        console.error('Graph generation error:', err);
      }
    }
  }, [mounted]);

  // Load machine data
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

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && machineId) {
      loadMachine();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, machineId]);

  // Compute highlighted node IDs based on query
  const highlightNodeIds = useMemo(() => {
    if (!graphData || !highlightQuery.trim()) {
      return new Set<string>();
    }

    const query = highlightQuery.toLowerCase().trim();
    const highlighted = new Set<string>();

    graphData.nodes.forEach((node) => {
      const nameMatch = node.name.toLowerCase().includes(query);
      const qualnameMatch = node.qualname.toLowerCase().includes(query);
      const fileMatch = node.file.toLowerCase().includes(query);
      
      if (nameMatch || qualnameMatch || fileMatch) {
        highlighted.add(node.id);
      }
    });

    return highlighted;
  }, [graphData, highlightQuery]);

  // Compute node statistics
  const nodeStats = useMemo(() => {
    if (!selectedNode || !graphData) {
      return { outgoing: 0, incoming: 0 };
    }

    const outgoing = graphData.links.filter((link) => link.source === selectedNode.id).length;
    const incoming = graphData.links.filter((link) => link.target === selectedNode.id).length;

    return { outgoing, incoming };
  }, [selectedNode, graphData]);

  const handleRegenerate = useCallback(() => {
    try {
      const seed = Math.floor(Math.random() * 1000000);
      const data = generateDummyCallGraph(seed);
      setGraphData(data);
      setSelectedNode(null);
      setHighlightQuery('');
      setGraphError(null);
      // Camera will auto-center via useEffect in CallGraph3D when data changes
      // But also explicitly reset after a short delay to ensure it happens
      setTimeout(() => {
        graphRef.current?.resetCamera();
      }, 600);
    } catch (err: any) {
      setGraphError(err.message || 'Failed to regenerate graph');
      console.error('Graph regeneration error:', err);
    }
  }, []);

  const handleResetCamera = useCallback(() => {
    graphRef.current?.resetCamera();
  }, []);

  const handleNodeClick = useCallback((node: GraphNode | null) => {
    setSelectedNode(node);
  }, []);

  // Get user only after mount to avoid hydration mismatch
  const user = mounted ? getCurrentUser() : null;

  // Check role access (only after mount to avoid hydration mismatch)
  if (mounted && (!user || !hasRole(user, 'TECHNICIAN'))) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p>This page is only accessible to TECHNICIAN and ADMIN users.</p>
      </div>
    );
  }

  // Show loading during SSR/hydration
  if (!mounted || loading) {
    return (
      <div className="p-8">
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  // Error state
  if (error && !machine) {
    return (
      <div className="p-8">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
        <Button onClick={() => router.push('/tech/error-debug')}>
          Return to Machine List
        </Button>
      </div>
    );
  }

  if (!machine) {
    return (
      <div className="p-8">
        <div className="text-center py-8">Machine not found</div>
        <Button onClick={() => router.push('/tech/error-debug')}>
          Return to Machine List
        </Button>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Navigation Tabs */}
      <ErrorDebugNav machineId={machineId} />
      
      {/* Main Content Area - Full width flex column */}
      <div className="flex-1 flex flex-col min-h-0 w-full overflow-hidden">
        {/* Toolbar - Fixed height, vertically centered */}
        <div className="h-14 flex items-center justify-center border-b bg-white flex-shrink-0">
          <div className="flex items-center gap-3 w-full max-w-5xl px-4">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium">Highlight query:</label>
              <input
                type="text"
                className="border rounded px-3 py-1.5 text-sm w-48"
                placeholder="Search function/file..."
                value={highlightQuery}
                onChange={(e) => setHighlightQuery(e.target.value)}
              />
            </div>
            <Button variant="outline" size="sm" onClick={handleRegenerate}>
              Randomize / Regenerate
            </Button>
            <Button variant="outline" size="sm" onClick={handleResetCamera}>
              Reset Camera
            </Button>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="show-labels"
                checked={showLabels}
                onChange={(e) => setShowLabels(e.target.checked)}
                className="rounded"
              />
              <label htmlFor="show-labels" className="text-sm font-medium cursor-pointer">
                Show labels
              </label>
            </div>
            {graphError && (
              <div className="text-sm text-red-600 ml-auto">
                Error: {graphError}
              </div>
            )}
          </div>
        </div>

        {/* Graph Canvas Area - Fills remaining height, no scrolling */}
        <div className="flex-1 min-h-0 relative bg-gray-900 overflow-hidden">
          <GraphErrorBoundary onReset={handleRegenerate}>
            {graphData ? (
              <CallGraph3D
                ref={graphRef}
                nodes={graphData.nodes}
                links={graphData.links}
                highlightNodeIds={highlightNodeIds}
                onNodeClick={handleNodeClick}
                showLabels={showLabels}
              />
            ) : (
              <div className="flex items-center justify-center h-full text-white">
                {graphError ? `Error: ${graphError}` : 'Generating graph...'}
              </div>
            )}
          </GraphErrorBoundary>

          {/* Details Panel - Absolute positioned overlay */}
          {selectedNode && (
            <div className="absolute top-4 right-4 w-80 bg-white border rounded-lg shadow-lg overflow-hidden" style={{ maxHeight: 'calc(100% - 2rem)' }}>
              <Card className="border-0 h-full flex flex-col">
                <CardHeader className="pb-3 flex-shrink-0">
                  <CardTitle className="text-lg">Node Details</CardTitle>
                </CardHeader>
                <CardContent className="overflow-y-auto flex-1 min-h-0">
                  <div className="space-y-3 text-sm">
                    <div>
                      <span className="font-medium">Function:</span>
                      <div className="mt-1 font-mono text-xs bg-gray-100 p-2 rounded">
                        {selectedNode.name}
                      </div>
                    </div>
                    <div>
                      <span className="font-medium">Qualified Name:</span>
                      <div className="mt-1 font-mono text-xs bg-gray-100 p-2 rounded break-all">
                        {selectedNode.qualname}
                      </div>
                    </div>
                    <div>
                      <span className="font-medium">File:</span>
                      <div className="mt-1 font-mono text-xs bg-gray-100 p-2 rounded break-all">
                        {selectedNode.file}
                      </div>
                    </div>
                    <div>
                      <span className="font-medium">Line:</span> {selectedNode.line}
                    </div>
                    <div>
                      <span className="font-medium">Group:</span> {selectedNode.group}
                    </div>
                    <div className="pt-2 border-t">
                      <div>
                        <span className="font-medium">Outgoing calls:</span> {nodeStats.outgoing}
                      </div>
                      <div>
                        <span className="font-medium">Incoming calls:</span> {nodeStats.incoming}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
