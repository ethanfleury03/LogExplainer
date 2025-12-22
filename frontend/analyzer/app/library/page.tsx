'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { listMachines } from '@/lib/api/error-debug-client';

export default function LibraryPage() {
  const router = useRouter();

  useEffect(() => {
    const redirectToFirstMachine = async () => {
      try {
        const machines = await listMachines();
        if (machines.length > 0) {
          // Redirect to first machine's library page
          router.replace(`/library/${machines[0].id}`);
        } else {
          // No machines, stay on this page to show empty state
        }
      } catch (err) {
        console.error('Failed to load machines:', err);
      }
    };
    
    redirectToFirstMachine();
  }, [router]);

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Error Library</h2>
      <div className="text-center text-muted-foreground">Loading...</div>
    </div>
  );
}

