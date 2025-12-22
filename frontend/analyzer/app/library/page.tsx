'use client';

import { useState, useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { listMachines, getMachineErrorKeys, type Machine } from '@/lib/api/error-debug-client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function LibraryPage() {
  const pathname = usePathname();
  const router = useRouter();
  const [machines, setMachines] = useState<Machine[]>([]);
  const [selectedMachine, setSelectedMachine] = useState<Machine | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingErrorKeys, setLoadingErrorKeys] = useState(false);
  const [errorKeys, setErrorKeys] = useState<Array<{ key: string; chunk_count: number }>>([]);

  // Get machine ID from URL - check if we're on /library/[machineId] or just /library
  // If just /library, we'll use the first machine or redirect to error debug
  const machineIdFromUrl = pathname?.match(/\/library\/([^\/]+)/)?.[1] || null;

  useEffect(() => {
    const loadMachines = async () => {
      try {
        const data = await listMachines();
        setMachines(data);
        
        // Select machine from URL or first available
        if (machineIdFromUrl) {
          const machine = data.find(m => m.id === machineIdFromUrl);
          if (machine) {
            // Only update if machine actually changed
            if (selectedMachine?.id !== machine.id) {
              setSelectedMachine(machine);
              // Clear error keys immediately when machine changes
              setErrorKeys([]);
            }
          } else if (data.length > 0) {
            // Machine not found, redirect to first machine
            router.replace(`/library/${data[0].id}`);
            return;
          }
        } else if (data.length > 0) {
          // No machine in URL, redirect to first machine
          router.replace(`/library/${data[0].id}`);
          return;
        }
      } catch (err) {
        console.error('Failed to load machines:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadMachines();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [machineIdFromUrl]); // Only depend on machineIdFromUrl - machine selection happens inside

  // Load error keys from selected machine's active index
  // This effect runs whenever selectedMachine.id changes
  useEffect(() => {
    if (!selectedMachine) {
      setErrorKeys([]);
      setLoadingErrorKeys(false);
      return;
    }

    if (!selectedMachine.active_version) {
      setErrorKeys([]);
      setLoadingErrorKeys(false);
      return;
    }

    // Clear previous results immediately when machine changes
    setErrorKeys([]);
    setLoadingErrorKeys(true);

    const loadErrorKeys = async () => {
      try {
        const data = await getMachineErrorKeys(selectedMachine.id);
        setErrorKeys(data.error_keys || []);
      } catch (err: any) {
        console.error('Failed to load error keys:', err);
        setErrorKeys([]);
      } finally {
        setLoadingErrorKeys(false);
      }
    };

    loadErrorKeys();
  }, [selectedMachine?.id]); // Only depend on machine ID - refreshes when machine changes

  if (loading) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">Error Library</h2>
        <div className="text-center text-muted-foreground">Loading machines...</div>
      </div>
    );
  }

  if (machines.length === 0) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">Error Library</h2>
        <div className="text-center text-muted-foreground">
          No machines found. Please add a machine and upload an index first.
        </div>
      </div>
    );
  }

  if (!selectedMachine) {
    return (
      <div className="p-6">
        <h2 className="text-2xl font-bold mb-4">Error Library</h2>
        <div className="text-center text-muted-foreground">No machine selected.</div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold">Error Library</h2>
        <div className="text-sm text-muted-foreground">
          Machine: <span className="font-medium">{selectedMachine.display_name}</span>
        </div>
      </div>
      
      {!selectedMachine.active_version ? (
        <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-3 rounded mb-4">
          No active index for this machine. Upload an index to view error keys.
        </div>
      ) : loadingErrorKeys ? (
        <div className="text-center text-muted-foreground py-8">Loading error keys...</div>
      ) : errorKeys.length === 0 ? (
        <div className="text-center text-muted-foreground py-8">
          <p>No error keys found in the active index.</p>
          <p className="text-sm mt-2">
            Total errors in index: {selectedMachine.active_version.total_errors || 0}
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

