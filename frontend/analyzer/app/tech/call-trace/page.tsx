'use client';

import { useState, useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import { listMachines, type Machine } from '@/lib/api/error-debug-client';

export default function CallTracePage() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadMachines = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listMachines();
      setMachines(data);
      
      if (data.length > 0 && pathname === '/tech/call-trace') {
        const urlParams = new URLSearchParams(window.location.search);
        const machineIdFromQuery = urlParams.get('machine');
        
        if (machineIdFromQuery && data.some(m => m.id === machineIdFromQuery)) {
          router.replace(`/tech/call-trace/${machineIdFromQuery}`);
        } else {
          router.replace(`/tech/call-trace/${data[0].id}`);
        }
        return;
      }
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to load machines';
      setError(errorMsg);
      console.error('Failed to load machines:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted) {
      loadMachines();
    }
  }, [mounted]);

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

  return (
    <div className="flex items-center justify-center h-full">
      <div className="text-center max-w-md">
        <h1 className="text-2xl font-bold mb-2">No machines yet</h1>
        <p className="text-muted-foreground mb-6">
          Use &quot;Add Machine&quot; in the left sidebar to create your first machine.
        </p>
        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4 text-sm">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

