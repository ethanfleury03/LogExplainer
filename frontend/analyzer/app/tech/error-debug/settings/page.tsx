'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { listMachines } from '@/lib/api/error-debug-client';

export default function SettingsRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    const redirectToMachineSettings = async () => {
      try {
        const machines = await listMachines();
        if (machines.length > 0) {
          // Redirect to first machine's settings page
          router.replace(`/tech/error-debug/${machines[0].id}/settings`);
        } else {
          // No machines, stay on this page to show empty state
        }
      } catch (err) {
        console.error('Failed to load machines:', err);
      }
    };
    
    redirectToMachineSettings();
  }, [router]);

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

