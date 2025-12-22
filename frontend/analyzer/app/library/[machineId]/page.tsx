'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { listMachines, getMachineErrorKeys, type Machine } from '@/lib/api/error-debug-client';
import { getCurrentUser, hasRole } from '@/lib/auth';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function LibraryMachinePage() {
  const params = useParams();
  const router = useRouter();
  const machineId = params.machineId as string;
  const user = getCurrentUser();
  
  const [machine, setMachine] = useState<Machine | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingErrorKeys, setLoadingErrorKeys] = useState(false);
  const [errorKeys, setErrorKeys] = useState<Array<{ key: string; chunk_count: number }>>([]);
  const [error, setError] = useState<string | null>(null);

  // Check role access
  if (!user || !hasRole(user, 'TECHNICIAN')) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p>This page is only accessible to TECHNICIAN and ADMIN users.</p>
      </div>
    );
  }

  // Clear all data when machineId changes - this ensures fresh data for the new machine
  useEffect(() => {
    // Clear previous machine's data immediately
    setMachine(null);
    setErrorKeys([]);
    setError(null);
    
    // Load new machine data
    loadMachine();
  }, [machineId]);

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

  // Load error keys from selected machine's active index
  // This effect runs whenever machine changes
  useEffect(() => {
    if (!machine) {
      setErrorKeys([]);
      setLoadingErrorKeys(false);
      return;
    }

    if (!machine.active_version) {
      setErrorKeys([]);
      setLoadingErrorKeys(false);
      return;
    }

    // Clear previous results immediately when machine changes
    setErrorKeys([]);
    setLoadingErrorKeys(true);

    const loadErrorKeys = async () => {
      try {
        const data = await getMachineErrorKeys(machine.id);
        setErrorKeys(data.error_keys || []);
      } catch (err: any) {
        console.error('Failed to load error keys:', err);
        setErrorKeys([]);
        setError(err.message || 'Failed to load error keys');
      } finally {
        setLoadingErrorKeys(false);
      }
    };

    loadErrorKeys();
  }, [machine?.id]); // Only depend on machine ID - refreshes when machine changes

  if (loading) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">Error Library</h2>
        <div className="text-center text-muted-foreground">Loading machine...</div>
      </div>
    );
  }

  if (error && !machine) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">Error Library</h2>
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      </div>
    );
  }

  if (!machine) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">Error Library</h2>
        <div className="text-center text-muted-foreground">Machine not found.</div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Error Library</h2>
        <div className="text-sm text-muted-foreground">
          Machine: <span className="font-medium">{machine.display_name}</span>
        </div>
      </div>
      
      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}
      
      {!machine.active_version ? (
        <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mb-4">
          No active index for this machine. Upload an index to view error keys.
        </div>
      ) : loadingErrorKeys ? (
        <div className="text-center text-muted-foreground py-8">Loading error keys...</div>
      ) : errorKeys.length === 0 ? (
        <div className="text-center text-muted-foreground py-8">
          <p>No error keys found in the active index.</p>
          <p className="text-sm mt-2">
            Total errors in index: {machine.active_version.total_errors || 0}
          </p>
        </div>
      ) : (
        <div className="grid gap-4">
          {errorKeys.map((ek, idx) => (
            <Card key={idx}>
              <CardHeader>
                <CardTitle className="text-base">{ek.key}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-muted-foreground">
                  <div>Chunks: {ek.chunk_count}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

