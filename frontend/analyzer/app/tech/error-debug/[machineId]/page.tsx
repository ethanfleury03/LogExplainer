'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import {
  listMachines,
  searchIndex,
  uploadVersion,
  emailIngestScript,
  type Machine,
} from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface SearchResult {
  error_key: string;
  chunks: Array<{
    chunk_id: string;
    function_name: string;
    class_name?: string;
    file_path: string;
    line_start: number;
    line_end: number;
    signature: string;
    code: string;
    docstring?: string;
    leading_comment?: string;
    error_messages: Array<{
      message: string;
      log_level: string;
      source_type: string;
    }>;
    log_levels: string[];
  }>;
  match_type: 'exact' | 'partial' | 'code_search';
  score: number;
  matched_text?: string;
}

export default function MachineSearchPage() {
  const params = useParams();
  const router = useRouter();
  const machineId = params.machineId as string;
  const [mounted, setMounted] = useState(false);
  
  const [machine, setMachine] = useState<Machine | null>(null);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedChunk, setSelectedChunk] = useState<SearchResult['chunks'][0] | null>(null);
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [emailAddress, setEmailAddress] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Define loadMachine before useEffect hooks (but after useState hooks)
  const loadMachine = async () => {
    try {
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
    }
  };

  // All hooks must be called before any conditional returns
  useEffect(() => {
    setMounted(true);
  }, []);

  // Clear all data when machineId changes - this ensures fresh data for the new machine
  useEffect(() => {
    if (!mounted) return; // Don't run during SSR
    
    // Clear previous machine's data immediately
    setMachine(null);
    setQuery('');
    setResults([]);
    setSelectedChunk(null);
    setExpandedKeys(new Set());
    setError(null);
    
    // Load new machine data
    loadMachine();
    
    // Check for upload query param
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('upload') === 'true') {
      setShowUploadModal(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [machineId, mounted]);

  // Get user only after mount to avoid hydration mismatch
  const user = mounted ? getCurrentUser() : null;

  // Check role access (only after mount to avoid hydration mismatch)
  // Conditional returns AFTER all hooks are called
  if (mounted && (!user || !hasRole(user, 'TECHNICIAN'))) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p>This page is only accessible to TECHNICIAN and ADMIN users.</p>
      </div>
    );
  }

  // Show loading during SSR/hydration
  if (!mounted) {
    return (
      <div className="p-8">
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  const handleSearch = async () => {
    if (!query.trim()) return;
    
    try {
      setSearching(true);
      setError(null);
      const response = await searchIndex(machineId, query);
      setResults(response.results);
      
      // Auto-expand first result
      if (response.results.length > 0) {
        setExpandedKeys(new Set([response.results[0].error_key]));
        if (response.results[0].chunks.length > 0) {
          setSelectedChunk(response.results[0].chunks[0]);
        }
      } else {
        setError('No results found. Try a different search query.');
      }
    } catch (err: any) {
      const errorMsg = err.message || 'Search failed';
      setError(errorMsg);
      console.error('Search failed:', err);
      
      if (errorMsg.includes('403') || errorMsg.includes('401')) {
        alert('Access denied. Please ensure you are logged in as TECHNICIAN or ADMIN.');
      } else if (errorMsg.includes('No active index')) {
        alert('No active index found. Please upload an index file first.');
      } else {
        alert(`Search failed: ${errorMsg}`);
      }
    } finally {
      setSearching(false);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setUploading(true);
      setError(null);
      await uploadVersion(machineId, file);
      setShowUploadModal(false);
      loadMachine(); // Refresh machine data
      alert('Index uploaded successfully!');
    } catch (err: any) {
      const errorMsg = err.message || 'Upload failed';
      setError(errorMsg);
      console.error('Upload failed:', err);
      
      // Show specific error messages
      if (errorMsg.includes('schema_version') || errorMsg.includes('created_at')) {
        alert(`Validation error: ${errorMsg}\n\nEnsure the index JSON includes schema_version and created_at fields.`);
      } else if (errorMsg.includes('Invalid JSON')) {
        alert(`Invalid JSON file: ${errorMsg}\n\nPlease upload a valid index.json file.`);
      } else if (errorMsg.includes('403') || errorMsg.includes('401')) {
        alert('Access denied. Please ensure you are logged in as TECHNICIAN or ADMIN.');
      } else {
        alert(`Upload failed: ${errorMsg}`);
      }
    } finally {
      setUploading(false);
    }
  };

  const handleEmailScript = async () => {
    if (!emailAddress.trim()) return;

    try {
      setError(null);
      await emailIngestScript(emailAddress);
      setShowEmailModal(false);
      setEmailAddress('');
      alert('Email sent successfully!');
    } catch (err: any) {
      setError(err.message || 'Failed to send email');
    }
  };

  const toggleExpand = (errorKey: string) => {
    const newExpanded = new Set(expandedKeys);
    if (newExpanded.has(errorKey)) {
      newExpanded.delete(errorKey);
    } else {
      newExpanded.add(errorKey);
    }
    setExpandedKeys(newExpanded);
  };

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return 'Never';
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  if (!machine) {
    return (
      <div className="p-8">
        {error ? (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        ) : (
          <div>Loading machine...</div>
        )}
      </div>
    );
  }

  const hasActiveIndex = !!machine.active_version;

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="border-b p-4 bg-white">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">{machine.display_name}</h1>
            <p className="text-sm text-gray-600">
              {machine.printer_model} • {machine.printing_type}
            </p>
            {hasActiveIndex && machine.active_version && (
              <p className="text-xs text-gray-500 mt-1">
                Active index: {formatDate(machine.active_version.indexed_at)} •{' '}
                {machine.active_version.total_chunks} chunks, {machine.active_version.total_errors} errors
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setShowEmailModal(true)}>
              Email Script
            </Button>
            <Button variant="outline" onClick={() => setShowUploadModal(true)}>
              {hasActiveIndex ? 'Update Index' : 'Upload Index'}
            </Button>
            <Button variant="outline" onClick={() => router.push('/tech/error-debug')}>
              Back to Machines
            </Button>
          </div>
        </div>
      </div>

      {!hasActiveIndex && (
        <div className="bg-yellow-50 border-b border-yellow-200 p-4">
          <div className="flex justify-between items-center">
            <div>
              <p className="text-yellow-800 font-medium">
                No active index uploaded. Upload one to search.
              </p>
              <p className="text-yellow-700 text-sm mt-1">
                Use the &quot;Upload Index&quot; button above or go to Versions to manage index files.
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowUploadModal(true)}
              >
                Upload Index
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => router.push(`/tech/error-debug/${machineId}/versions`)}
              >
                View Versions
              </Button>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-100 border-b border-red-400 text-red-700 px-4 py-3">
          {error}
        </div>
      )}

      {/* Main Content - Tri-pane layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Search */}
        <div className="w-1/3 border-r p-4 overflow-y-auto">
          <div className="mb-4">
            <label className="block text-sm font-medium mb-2">Search Error Message</label>
            <div className="flex gap-2">
              <input
                type="text"
                className="flex-1 border rounded px-3 py-2"
                placeholder="Paste error message here..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                disabled={!hasActiveIndex || searching}
              />
              <Button onClick={handleSearch} disabled={!hasActiveIndex || searching}>
                {searching ? 'Searching...' : 'Search'}
              </Button>
            </div>
          </div>

          {results.length > 0 && (
            <div>
              <div className="mb-3 p-2 bg-gray-50 rounded border">
                <div className="text-xs font-medium text-gray-700 mb-1">Search:</div>
                <div className="text-xs text-gray-900 break-words">{query}</div>
              </div>
              <h3 className="font-medium mb-2">Results ({results.length})</h3>
              <div className="space-y-2">
                {results.map((result, idx) => (
                  <Card
                    key={idx}
                    className={`p-3 cursor-pointer ${
                      expandedKeys.has(result.error_key) ? 'bg-blue-50' : ''
                    }`}
                    onClick={() => toggleExpand(result.error_key)}
                  >
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="font-medium text-sm">{result.error_key}</div>
                        {result.matched_text && (
                          <div className="mt-1 p-1.5 bg-yellow-50 border border-yellow-200 rounded text-xs">
                            <div className="font-medium text-gray-700 mb-0.5">Match:</div>
                            <div className="text-gray-900 break-words">{result.matched_text}</div>
                          </div>
                        )}
                        <div className="text-xs text-gray-500 mt-1">
                          {result.chunks.length} chunk(s) • {result.match_type} match
                        </div>
                      </div>
                      {result.match_type === 'exact' && (
                        <span className="text-xs bg-green-100 text-green-800 px-2 py-1 rounded">
                          Exact
                        </span>
                      )}
                    </div>
                    {expandedKeys.has(result.error_key) && (
                      <div className="mt-2 space-y-1">
                        {result.chunks.map((chunk, chunkIdx) => (
                          <div
                            key={chunkIdx}
                            className={`text-xs p-2 rounded cursor-pointer ${
                              selectedChunk?.chunk_id === chunk.chunk_id
                                ? 'bg-blue-200'
                                : 'bg-gray-100 hover:bg-gray-200'
                            }`}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedChunk(chunk);
                            }}
                          >
                            <div className="font-medium">{chunk.function_name}</div>
                            <div className="text-gray-600 truncate">{chunk.file_path}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Middle: Results list (if needed) */}
        <div className="w-1/3 border-r p-4 overflow-y-auto">
          {selectedChunk ? (
            <div>
              <h3 className="font-medium mb-2">Selected Function</h3>
              <div className="text-sm">
                <div className="mb-2">
                  <span className="font-medium">Function:</span> {selectedChunk.function_name}
                </div>
                {selectedChunk.class_name && (
                  <div className="mb-2">
                    <span className="font-medium">Class:</span> {selectedChunk.class_name}
                  </div>
                )}
                <div className="mb-2">
                  <span className="font-medium">File:</span> {selectedChunk.file_path}
                </div>
                <div className="mb-2">
                  <span className="font-medium">Lines:</span> {selectedChunk.line_start}-
                  {selectedChunk.line_end}
                </div>
                {selectedChunk.signature && (
                  <div className="mb-2">
                    <span className="font-medium">Signature:</span>
                    <pre className="text-xs bg-gray-100 p-2 rounded mt-1 overflow-x-auto">
                      {selectedChunk.signature}
                    </pre>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-gray-500 text-center py-8">
              Select a chunk from the results to view details
            </div>
          )}
        </div>

        {/* Right: Details pane */}
        <div className="w-1/3 p-4 overflow-y-auto">
          {selectedChunk ? (
            <Tabs defaultValue="code">
              <TabsList>
                <TabsTrigger value="summary">Summary</TabsTrigger>
                <TabsTrigger value="code">Code</TabsTrigger>
                <TabsTrigger value="metadata">Metadata</TabsTrigger>
                <TabsTrigger value="raw">Raw</TabsTrigger>
              </TabsList>
              <TabsContent value="summary" className="mt-4">
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="font-medium">Function:</span> {selectedChunk.function_name}
                  </div>
                  {selectedChunk.class_name && (
                    <div>
                      <span className="font-medium">Class:</span> {selectedChunk.class_name}
                    </div>
                  )}
                  <div>
                    <span className="font-medium">File:</span> {selectedChunk.file_path}
                  </div>
                  <div>
                    <span className="font-medium">Location:</span> Lines {selectedChunk.line_start}-
                    {selectedChunk.line_end}
                  </div>
                  {selectedChunk.docstring && (
                    <div>
                      <span className="font-medium">Docstring:</span>
                      <pre className="text-xs bg-gray-100 p-2 rounded mt-1 whitespace-pre-wrap">
                        {selectedChunk.docstring}
                      </pre>
                    </div>
                  )}
                  {selectedChunk.error_messages.length > 0 && (
                    <div>
                      <span className="font-medium">Error Messages:</span>
                      <ul className="list-disc list-inside mt-1">
                        {selectedChunk.error_messages.map((err, idx) => (
                          <li key={idx} className="text-xs">
                            {err.message} ({err.log_level}, {err.source_type})
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </TabsContent>
              <TabsContent value="code" className="mt-4">
                <pre className="text-xs bg-gray-100 p-4 rounded overflow-x-auto">
                  {selectedChunk.code}
                </pre>
              </TabsContent>
              <TabsContent value="metadata" className="mt-4">
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="font-medium">Chunk ID:</span> {selectedChunk.chunk_id}
                  </div>
                  <div>
                    <span className="font-medium">Log Levels:</span>{' '}
                    {selectedChunk.log_levels.join(', ') || 'None'}
                  </div>
                  {selectedChunk.leading_comment && (
                    <div>
                      <span className="font-medium">Leading Comment:</span>
                      <pre className="text-xs bg-gray-100 p-2 rounded mt-1 whitespace-pre-wrap">
                        {selectedChunk.leading_comment}
                      </pre>
                    </div>
                  )}
                </div>
              </TabsContent>
              <TabsContent value="raw" className="mt-4">
                <pre className="text-xs bg-gray-100 p-4 rounded overflow-x-auto">
                  {JSON.stringify(selectedChunk, null, 2)}
                </pre>
              </TabsContent>
            </Tabs>
          ) : (
            <div className="text-gray-500 text-center py-8">
              No chunk selected
            </div>
          )}
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">Upload Index</h2>
            <input
              type="file"
              accept=".json"
              onChange={handleUpload}
              disabled={uploading}
              className="mb-4"
            />
            {uploading && <p className="text-sm text-gray-600">Uploading...</p>}
            <Button onClick={() => setShowUploadModal(false)} disabled={uploading}>
              Close
            </Button>
          </Card>
        </div>
      )}

      {/* Email Modal */}
      {showEmailModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">Email Script</h2>
            <div className="mb-4">
              <label className="block text-sm font-medium mb-1">Email Address</label>
              <input
                type="email"
                className="w-full border rounded px-3 py-2"
                value={emailAddress}
                onChange={(e) => setEmailAddress(e.target.value)}
                placeholder="technician@example.com"
              />
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setShowEmailModal(false)}>
                Cancel
              </Button>
              <Button onClick={handleEmailScript}>Send</Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

