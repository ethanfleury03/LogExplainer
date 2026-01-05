'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { listMachines } from '@/lib/api/error-debug-client';

export default function SettingsRedirectPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const redirectToMachineSettings = async () => {
      try {
        // Check if we're already on a machine-specific settings page
        const machineIdMatch = pathname?.match(/\/tech\/error-debug\/([^\/]+)\/settings/);
        if (machineIdMatch) {
          // Already on a machine settings page, no redirect needed
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
              console.log('[SettingsRedirectPage] Redirecting to preserve machine from query param:', machineIdFromQuery);
            }
            router.replace(`/tech/error-debug/${machineIdFromQuery}/settings`);
          } else {
            // Only redirect to first machine if no valid machine ID found
            if (process.env.NODE_ENV === 'development') {
              console.log('[SettingsRedirectPage] Redirecting to default machine (no machine ID found):', machines[0].id, 'reason: default_init');
            }
            router.replace(`/tech/error-debug/${machines[0].id}/settings`);
          }
        } else {
          // No machines, stay on this page to show empty state
        }
      } catch (err) {
        console.error('Failed to load machines:', err);
      }
    };
    
    redirectToMachineSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, pathname]);

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Settings</h2>
      <div className="text-center text-muted-foreground py-8">
        <p className="mb-4">Select a machine to edit settings.</p>
        <p className="text-sm">Use the machine sidebar to select a machine, or settings will load automatically if machines exist.</p>
      </div>
    </div>
  );
}

