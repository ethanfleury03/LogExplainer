'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { listMachines } from '@/lib/api/error-debug-client';

export default function LibraryPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const redirectToFirstMachine = async () => {
      try {
        // Check if we're already on a machine-specific library page
        const machineIdMatch = pathname?.match(/\/library\/([^\/]+)/);
        if (machineIdMatch) {
          // Already on a machine library page, no redirect needed
          return;
        }

        const machines = await listMachines();
        if (machines.length > 0) {
          // Check if there's a machine ID in query params (preserved from navigation)
          const urlParams = new URLSearchParams(window.location.search);
          const machineIdFromQuery = urlParams.get('machine');
          
          // Only redirect if no machine ID in URL and no valid machine in query
          // This prevents resetting selection when navigating between tabs
          if (machineIdFromQuery && machines.some(m => m.id === machineIdFromQuery)) {
            // Preserve machine from query param if valid
            if (process.env.NODE_ENV === 'development') {
              console.log('[LibraryPage] Redirecting to preserve machine from query param:', machineIdFromQuery);
            }
            router.replace(`/library/${machineIdFromQuery}`);
          } else {
            // Only redirect to first machine if no valid machine ID found
            if (process.env.NODE_ENV === 'development') {
              console.log('[LibraryPage] Redirecting to default machine (no machine ID found):', machines[0].id, 'reason: default_init');
            }
            router.replace(`/library/${machines[0].id}`);
          }
        } else {
          // No machines, stay on this page to show empty state
        }
      } catch (err) {
        console.error('Failed to load machines:', err);
      }
    };
    
    redirectToFirstMachine();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, pathname]);

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Error Library</h2>
      <div className="text-center text-muted-foreground">Loading...</div>
    </div>
  );
}

