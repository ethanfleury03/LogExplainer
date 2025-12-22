'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import { listMachines, createMachine, updateMachine, deleteMachine, type Machine } from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export default function ErrorDebugPage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  
  useEffect(() => {
    setMounted(true);
  }, []);
  
  const user = mounted ? getCurrentUser() : null;
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingMachine, setEditingMachine] = useState<Machine | null>(null);
  const [newMachine, setNewMachine] = useState({
    display_name: '',
    printer_model: '',
    printing_type: '',
  });

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
  if (!mounted) {
    return (
      <div className="p-8">
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  useEffect(() => {
    loadMachines();
  }, []);

  const loadMachines = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listMachines();
      setMachines(data);
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to load machines';
      setError(errorMsg);
      console.error('Failed to load machines:', err);
      // Show toast/alert for 401/403/500
      if (err.message?.includes('403') || err.message?.includes('401')) {
        alert('Access denied. Please ensure you are logged in as TECHNICIAN or ADMIN.');
      } else if (err.message?.includes('500')) {
        alert('Server error. Please check backend logs.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCreateMachine = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createMachine(newMachine);
      setShowAddModal(false);
      setNewMachine({ display_name: '', printer_model: '', printing_type: '' });
      loadMachines();
    } catch (err: any) {
      setError(err.message || 'Failed to create machine');
    }
  };

  const handleUpdateMachine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingMachine) return;
    try {
      await updateMachine(editingMachine.id, newMachine);
      setShowEditModal(false);
      setEditingMachine(null);
      setNewMachine({ display_name: '', printer_model: '', printing_type: '' });
      loadMachines();
    } catch (err: any) {
      setError(err.message || 'Failed to update machine');
    }
  };

  const handleDeleteMachine = async (machineId: string) => {
    if (!confirm('Are you sure you want to delete this machine and all its index versions?')) {
      return;
    }
    try {
      await deleteMachine(machineId);
      loadMachines();
    } catch (err: any) {
      setError(err.message || 'Failed to delete machine');
    }
  };

  const formatDate = (dateStr: string | undefined) => {
    if (!dateStr) return 'Never';
    try {
      return new Date(dateStr).toLocaleDateString();
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Error Debug - Machines</h1>
        <Button onClick={() => setShowAddModal(true)}>Add Machine</Button>
      </div>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8">Loading machines...</div>
      ) : (
        <Card className="p-6">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b">
                <th className="text-left p-2">Name</th>
                <th className="text-left p-2">Printer Model</th>
                <th className="text-left p-2">Printing Type</th>
                <th className="text-left p-2">Active Indexed At</th>
                <th className="text-left p-2">Chunks</th>
                <th className="text-left p-2">Errors</th>
                <th className="text-left p-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {machines.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center p-8 text-gray-500">
                    No machines found. Click &quot;Add Machine&quot; to create one.
                  </td>
                </tr>
              ) : (
                machines.map((machine) => (
                  <tr key={machine.id} className="border-b hover:bg-gray-50">
                    <td className="p-2 font-medium">{machine.display_name}</td>
                    <td className="p-2">{machine.printer_model}</td>
                    <td className="p-2">{machine.printing_type}</td>
                    <td className="p-2">
                      {formatDate(machine.active_version?.indexed_at)}
                    </td>
                    <td className="p-2">
                      {machine.active_version?.total_chunks || 0}
                    </td>
                    <td className="p-2">
                      {machine.active_version?.total_errors || 0}
                    </td>
                    <td className="p-2">
                      <div className="flex gap-2 flex-wrap">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => router.push(`/tech/error-debug/${machine.id}`)}
                        >
                          Search
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            // Navigate to search page and trigger upload
                            router.push(`/tech/error-debug/${machine.id}?upload=true`);
                          }}
                        >
                          Upload/Update Index
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => router.push(`/tech/error-debug/${machine.id}/versions`)}
                        >
                          Versions
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditingMachine(machine);
                            setNewMachine({
                              display_name: machine.display_name,
                              printer_model: machine.printer_model,
                              printing_type: machine.printing_type,
                            });
                            setShowEditModal(true);
                          }}
                        >
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDeleteMachine(machine.id)}
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Card>
      )}

      {showAddModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">Add Machine</h2>
            <form onSubmit={handleCreateMachine}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Display Name *</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded px-3 py-2"
                  value={newMachine.display_name}
                  onChange={(e) => setNewMachine({ ...newMachine, display_name: e.target.value })}
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Printer Model *</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded px-3 py-2"
                  value={newMachine.printer_model}
                  onChange={(e) => setNewMachine({ ...newMachine, printer_model: e.target.value })}
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Printing Type *</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded px-3 py-2"
                  value={newMachine.printing_type}
                  onChange={(e) => setNewMachine({ ...newMachine, printing_type: e.target.value })}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button type="button" variant="outline" onClick={() => setShowAddModal(false)}>
                  Cancel
                </Button>
                <Button type="submit">Create</Button>
              </div>
            </form>
          </Card>
        </div>
      )}

      {showEditModal && editingMachine && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">Edit Machine</h2>
            <form onSubmit={handleUpdateMachine}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Display Name *</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded px-3 py-2"
                  value={newMachine.display_name}
                  onChange={(e) => setNewMachine({ ...newMachine, display_name: e.target.value })}
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Printer Model *</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded px-3 py-2"
                  value={newMachine.printer_model}
                  onChange={(e) => setNewMachine({ ...newMachine, printer_model: e.target.value })}
                />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Printing Type *</label>
                <input
                  type="text"
                  required
                  className="w-full border rounded px-3 py-2"
                  value={newMachine.printing_type}
                  onChange={(e) => setNewMachine({ ...newMachine, printing_type: e.target.value })}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowEditModal(false);
                    setEditingMachine(null);
                    setNewMachine({ display_name: '', printer_model: '', printing_type: '' });
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit">Update</Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}

