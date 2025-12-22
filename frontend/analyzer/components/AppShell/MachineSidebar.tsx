'use client';

import { useState, useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { User } from '@/lib/types';
import { hasRole } from '@/lib/auth';
import { listMachines, createMachine, type Machine } from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Plus, Printer, Upload } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MachineSidebarProps {
  user: User | null;
}

export function MachineSidebar({ user }: MachineSidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [newMachine, setNewMachine] = useState({
    display_name: '',
    printer_model: '',
    printing_type: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [uploadingMachineId, setUploadingMachineId] = useState<string | null>(null);

  // Ensure component only renders on client to avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  // Check if we should show the sidebar (must be after all hooks)
  const isErrorDebugArea = mounted && pathname?.startsWith('/tech/error-debug') || false;
  const shouldShow = isErrorDebugArea && user && hasRole(user, 'TECHNICIAN');

  // Extract machine ID from pathname if on error-debug page
  const selectedMachineId = pathname?.match(/\/tech\/error-debug\/([^\/]+)/)?.[1] || null;

  const loadMachines = async () => {
    if (!shouldShow) return; // Don't load if not showing
    
    try {
      setLoading(true);
      setError(null);
      
      // Log API URL for debugging
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      console.log('MachineSidebar: Fetching machines from', `${apiUrl}/api/error-debug/machines`);
      
      const data = await listMachines();
      setMachines(data);
      console.log(`MachineSidebar: Loaded ${data.length} machines`);
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to load machines';
      console.error('MachineSidebar: Failed to load machines:', err);
      console.error('MachineSidebar: Error details:', {
        message: err.message,
        stack: err.stack,
        name: err.name,
      });
      
      // Provide helpful error messages
      if (errorMsg.includes('403') || errorMsg.includes('401')) {
        setError('Access denied. Check auth headers.');
      } else if (errorMsg.includes('Failed to fetch') || errorMsg.includes('NetworkError') || err.name === 'TypeError') {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        setError(`Backend unreachable at ${apiUrl}. Is the backend running?`);
      } else {
        setError(errorMsg);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (shouldShow && mounted) {
      loadMachines();
    }
  }, [shouldShow, mounted]);

  // Refresh machines when pathname changes (e.g., after navigation)
  useEffect(() => {
    if (shouldShow && isErrorDebugArea && mounted) {
      loadMachines();
    }
  }, [pathname, shouldShow, isErrorDebugArea, mounted]);

  // Handle ?add=1 query param to auto-open Add Machine modal
  useEffect(() => {
    if (mounted && shouldShow && pathname === '/tech/error-debug') {
      // Check URL for ?add=1 query param
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get('add') === '1') {
        setShowAddModal(true);
        // Remove query param from URL immediately to prevent modal reopening on refresh
        router.replace('/tech/error-debug', { scroll: false });
      }
    }
  }, [mounted, shouldShow, pathname, router]);


  const handleCreateMachine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMachine.display_name.trim()) {
      setError('Machine name is required');
      return;
    }

    try {
      setError(null);
      const created = await createMachine({
        display_name: newMachine.display_name.trim(),
        printer_model: newMachine.printer_model.trim() || 'Unknown',
        printing_type: newMachine.printing_type.trim() || 'Unknown',
      });
      setShowAddModal(false);
      setNewMachine({ display_name: '', printer_model: '', printing_type: '' });
      await loadMachines();
      // Navigate to the new machine's error debug page
      router.push(`/tech/error-debug/${created.id}`);
    } catch (err: any) {
      setError(err.message || 'Failed to create machine');
      console.error('Failed to create machine:', err);
    }
  };

  const handleMachineClick = (machineId: string) => {
    router.push(`/tech/error-debug/${machineId}`);
  };

  const handleUploadClick = (e: React.MouseEvent, machineId: string) => {
    e.stopPropagation(); // Prevent machine selection
    setUploadingMachineId(machineId);
    fileInputRef.current?.click();
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !uploadingMachineId) return;

    try {
      setError(null);
      // Import uploadVersion dynamically to avoid circular deps
      const { uploadVersion } = await import('@/lib/api/error-debug-client');
      await uploadVersion(uploadingMachineId, file);
      // Refresh machine list and navigate to the machine's page
      await loadMachines();
      router.push(`/tech/error-debug/${uploadingMachineId}`);
      alert('Index uploaded successfully!');
    } catch (err: any) {
      const errorMsg = err.message || 'Upload failed';
      setError(errorMsg);
      console.error('Upload failed:', err);
      alert(`Upload failed: ${errorMsg}`);
    } finally {
      setUploadingMachineId(null);
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  // Early return AFTER all hooks are called
  // Also return null during SSR to avoid hydration mismatch
  if (!mounted || !shouldShow) {
    return null;
  }

  return (
    <>
      <div className="w-64 border-r bg-muted/20 h-full flex flex-col">
        {/* Header */}
        <div className="p-4 border-b">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              Machines
            </h2>
          </div>
          <Button
            size="sm"
            onClick={() => setShowAddModal(true)}
            className="w-full"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Machine
          </Button>
        </div>

        {/* Machine List */}
        <div className="flex-1 overflow-y-auto p-2">
          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="h-12 bg-muted animate-pulse rounded-md"
                />
              ))}
            </div>
          ) : error && machines.length === 0 ? (
            <div className="text-sm text-destructive text-center py-4 px-2">
              <p className="mb-2">{error}</p>
              <Button
                size="sm"
                variant="outline"
                onClick={loadMachines}
              >
                Retry
              </Button>
            </div>
          ) : machines.length === 0 ? (
            <div className="text-sm text-muted-foreground text-center py-8 px-2">
              <p className="mb-2">No machines yet</p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowAddModal(true)}
              >
                Add Machine
              </Button>
            </div>
          ) : (
            <div className="space-y-1">
              {machines.map((machine) => {
                const isSelected = selectedMachineId === machine.id;
                return (
                  <div
                    key={machine.id}
                    className={cn(
                      'group rounded-md transition-colors',
                      isSelected && 'bg-primary/10'
                    )}
                  >
                    <button
                      onClick={() => handleMachineClick(machine.id)}
                      className={cn(
                        'w-full text-left px-3 py-2 rounded-md text-sm transition-colors',
                        'hover:bg-accent hover:text-accent-foreground',
                        isSelected
                          ? 'bg-primary text-primary-foreground font-medium'
                          : 'text-muted-foreground'
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <Printer className="h-4 w-4 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="truncate font-medium">{machine.display_name}</div>
                          {machine.printer_model && (
                            <div className="text-xs opacity-70 truncate">
                              {machine.printer_model}
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                    {isSelected && (
                      <div className="px-3 pb-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="w-full text-xs"
                          onClick={(e) => handleUploadClick(e, machine.id)}
                          disabled={uploadingMachineId === machine.id}
                        >
                          <Upload className="h-3 w-3 mr-1" />
                          {uploadingMachineId === machine.id ? 'Uploading...' : 'Upload Index'}
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Hidden file input for upload */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={handleFileSelect}
        />
      </div>

      {/* Add Machine Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">Add Machine</h2>
            {error && (
              <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4 text-sm">
                {error}
              </div>
            )}
            <form onSubmit={handleCreateMachine}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">
                  Name <span className="text-destructive">*</span>
                </label>
                <input
                  type="text"
                  required
                  className="w-full border rounded px-3 py-2"
                  placeholder="e.g., Printer A"
                  value={newMachine.display_name}
                  onChange={(e) => setNewMachine({ ...newMachine, display_name: e.target.value })}
                  autoFocus
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Printer Model</label>
                <input
                  type="text"
                  className="w-full border rounded px-3 py-2"
                  placeholder="e.g., Model XYZ"
                  value={newMachine.printer_model}
                  onChange={(e) => setNewMachine({ ...newMachine, printer_model: e.target.value })}
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Printing Type</label>
                <input
                  type="text"
                  className="w-full border rounded px-3 py-2"
                  placeholder="e.g., Duraflex"
                  value={newMachine.printing_type}
                  onChange={(e) => setNewMachine({ ...newMachine, printing_type: e.target.value })}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowAddModal(false);
                    setError(null);
                    setNewMachine({ display_name: '', printer_model: '', printing_type: '' });
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit">Create</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </>
  );
}

