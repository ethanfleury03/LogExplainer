'use client';

import { usePathname, useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

interface ErrorDebugNavProps {
  machineId: string;
}

export function ErrorDebugNav({ machineId }: ErrorDebugNavProps) {
  const pathname = usePathname();
  const router = useRouter();

  const navItems = [
    { id: 'search', label: 'Search', path: `/tech/error-debug/${machineId}` },
    { id: 'versions', label: 'Versions', path: `/tech/error-debug/${machineId}/versions` },
    { id: 'settings', label: 'Settings', path: `/tech/error-debug/${machineId}/settings` },
  ];

  const isActive = (path: string) => {
    if (path === `/tech/error-debug/${machineId}`) {
      // Exact match for search page (base path)
      return pathname === path;
    }
    // For sub-routes, check if pathname starts with the path
    return pathname?.startsWith(path);
  };

  return (
    <div className="border-b bg-white">
      <div className="flex gap-1 px-4">
        {navItems.map((item) => {
          const active = isActive(item.path);
          return (
            <Button
              key={item.id}
              variant="ghost"
              onClick={() => router.push(item.path)}
              className={cn(
                'rounded-none border-b-2 border-transparent px-4 py-2',
                active
                  ? 'border-primary text-primary font-medium'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {item.label}
            </Button>
          );
        })}
      </div>
    </div>
  );
}

