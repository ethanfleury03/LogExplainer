'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import {
  listMachines,
  listVersions,
  activateVersion,
  deleteVersion,
  downloadVersion,
  type Machine,
  type MachineVersion,
} from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

export default function VersionsPage() {
  const params = useParams();
  const router = useRouter();
  const machineId = params.machineId as string;
  const user = getCurrentUser();
  
  const [machine, setMachine] = useState<Machine | null>(null);
  const [versions, setVersions] = useState<MachineVersion[]>([]);
  const [loading, setLoading] = useState(true);
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

  useEffect(() => {
    loadData();
  }, [machineId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [machinesData, versionsData] = await Promise.all([
        listMachines(),
        listVersions(machineId),
      ]);
      
      const found = machinesData.find((m) => m.id === machineId);
      if (!found) {
        setError('Machine not found');
        return;
      }
      
      setMachine(found);
      setVersions(versionsData);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleActivate = async (versionId: string) => {
    try {
      await activateVersion(machineId, versionId);
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to activate version');
    }
  };

  const handleDelete = async (versionId: string) => {
    if (!confirm('Are you sure you want to delete this version?')) {
      return;
    }
    try {
      await deleteVersion(machineId, versionId);
      loadData();
    } catch (err: any) {
      setError(err.message || 'Failed to delete version');
    }
  };

  const handleDownload = async (versionId: string) => {
    try {
      const blob = await downloadVersion(machineId, versionId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `index_${versionId}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setError(err.message || 'Failed to download version');
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return <div className="p-8">Loading...</div>;
  }

  if (!machine) {
    return (
      <div className="p-8">
        {error ? (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        ) : (
          <div>Machine not found</div>
        )}
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold">{machine.display_name} - Versions</h1>
          <p className="text-gray-600 mt-1">
            {machine.printer_model} • {machine.printing_type}
          </p>
        </div>
        <Button variant="outline" onClick={() => router.push(`/tech/error-debug/${machineId}`)}>
          Back to Search
        </Button>
      </div>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          {error}
        </div>
      )}

      <Card className="p-6">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b">
              <th className="text-left p-2">Indexed At</th>
              <th className="text-left p-2">Schema Version</th>
              <th className="text-left p-2">Chunks</th>
              <th className="text-left p-2">Errors</th>
              <th className="text-left p-2">Status</th>
              <th className="text-left p-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {versions.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center p-8 text-gray-500">
                  No versions found. Upload an index to get started.
                </td>
              </tr>
            ) : (
              versions.map((version) => (
                <tr key={version.id} className="border-b hover:bg-gray-50">
                  <td className="p-2">{formatDate(version.indexed_at)}</td>
                  <td className="p-2">{version.schema_version}</td>
                  <td className="p-2">{version.total_chunks}</td>
                  <td className="p-2">{version.total_errors}</td>
                  <td className="p-2">
                    {version.is_active ? (
                      <span className="bg-green-100 text-green-800 px-2 py-1 rounded text-xs">
                        Active
                      </span>
                    ) : (
                      <span className="text-gray-500 text-xs">Inactive</span>
                    )}
                  </td>
                  <td className="p-2">
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDownload(version.id)}
                      >
                        Download
                      </Button>
                      {!version.is_active && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleActivate(version.id)}
                        >
                          Activate
                        </Button>
                      )}
                      {!version.is_active && (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleDelete(version.id)}
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

