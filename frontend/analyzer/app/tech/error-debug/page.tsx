'use client';

import { useState, useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { getCurrentUser, hasRole } from '@/lib/auth';
import { listMachines, type Machine } from '@/lib/api/error-debug-client';
import { Button } from '@/components/ui/button';

export default function ErrorDebugPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Define loadMachines before useEffect (but after all useState hooks)
  const loadMachines = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listMachines();
      setMachines(data);
      
      // Only redirect if:
      // 1. We're on the base /tech/error-debug page (not a specific machine or sub-route)
      // 2. Machines exist
      // 3. There's no machine ID in the URL already (shouldn't happen, but guard against it)
      // This ensures we only redirect when truly uninitialized, not when navigating between tabs
      if (data.length > 0 && pathname === '/tech/error-debug') {
        // Check if there's a machine ID in query params (fallback for edge cases)
        const urlParams = new URLSearchParams(window.location.search);
        const machineIdFromQuery = urlParams.get('machine');
        
        if (machineIdFromQuery && data.some(m => m.id === machineIdFromQuery)) {
          // Preserve machine from query param if valid
          if (process.env.NODE_ENV === 'development') {
            console.log('[ErrorDebugPage] Redirecting to preserve machine from query param:', machineIdFromQuery);
          }
          router.replace(`/tech/error-debug/${machineIdFromQuery}`);
        } else {
          // Only redirect to first machine if no valid machine ID found
          if (process.env.NODE_ENV === 'development') {
            console.log('[ErrorDebugPage] Redirecting to default machine (no machine ID found):', data[0].id, 'reason: default_init');
          }
          router.replace(`/tech/error-debug/${data[0].id}`);
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

  // All hooks must be called before any conditional returns
  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted) {
      loadMachines();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted]);

  // Get user only after mount to avoid hydration mismatch
  const user = mounted ? getCurrentUser() : null;

  // Check role access (only after mount to avoid hydration mismatch)
  // This conditional return happens AFTER all hooks are called
  if (mounted && (!user || !hasRole(user, 'TECHNICIAN'))) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">Access Denied</h1>
        <p>This page is only accessible to TECHNICIAN and ADMIN users.</p>
      </div>
    );
  }
  
  // Show loading during SSR/hydration
  // This conditional return happens AFTER all hooks are called
  if (!mounted || loading) {
    return (
      <div className="p-8">
        <div className="text-center py-8">Loading...</div>
      </div>
    );
  }

  // Empty state: no machines exist
  // If we reach here, machines.length === 0 (redirect already happened if machines exist)
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
        <Button
          onClick={() => {
            // Navigate with query param to trigger MachineSidebar modal
            router.push('/tech/error-debug?add=1');
          }}
        >
          Add Machine
        </Button>
      </div>
    </div>
  );
}

