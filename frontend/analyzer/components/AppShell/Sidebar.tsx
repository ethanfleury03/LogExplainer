'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { User } from '@/lib/types';
import { hasRole } from '@/lib/auth';
import { BookOpen, Settings, Database, Bug } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SidebarProps {
  user: User | null;
}

const navItems = [
  { href: '/tech/error-debug', label: 'Error Debug', icon: Bug, roles: ['ADMIN', 'TECHNICIAN'] as const },
  { href: '/library', label: 'Error Library', icon: BookOpen, roles: ['ADMIN', 'TECHNICIAN'] as const },
  { href: '/index-manager', label: 'Index Manager', icon: Database, roles: ['ADMIN'] as const },
  { href: '/tech/error-debug/settings', label: 'Settings', icon: Settings, roles: ['ADMIN', 'TECHNICIAN'] as const },
];

export function Sidebar({ user }: SidebarProps) {
  const pathname = usePathname();

  // Extract machine ID from current pathname to preserve it in navigation
  const extractMachineId = (path: string | null): string | null => {
    if (!path) return null;
    // Match /tech/error-debug/[machineId] or /library/[machineId]
    const errorDebugMatch = path.match(/\/tech\/error-debug\/([^\/]+)/);
    const libraryMatch = path.match(/\/library\/([^\/]+)/);
    return errorDebugMatch?.[1] || libraryMatch?.[1] || null;
  };

  const currentMachineId = extractMachineId(pathname);

  // Build href that preserves machine ID when navigating
  const buildHref = (baseHref: string): string => {
    // If we have a machine ID and the base href is a route that supports machine IDs
    if (currentMachineId) {
      if (baseHref === '/tech/error-debug') {
        // Preserve machine ID when navigating to Error Debug
        return `/tech/error-debug/${currentMachineId}`;
      } else if (baseHref === '/tech/error-debug/settings') {
        // Preserve machine ID when navigating to Settings
        return `/tech/error-debug/${currentMachineId}/settings`;
      } else if (baseHref === '/library') {
        // Preserve machine ID when navigating to Library
        return `/library/${currentMachineId}`;
      }
    }
    // Otherwise use base href (will trigger redirect logic if needed)
    return baseHref;
  };

  return (
    <div className="w-64 border-r bg-muted/30 h-full flex flex-col">
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          if (!user || !item.roles.some((role) => hasRole(user, role))) {
            return null;
          }

          // Special handling for Settings: active if on any settings route under error-debug
          const isActive = item.href === '/tech/error-debug/settings'
            ? pathname?.startsWith('/tech/error-debug') && pathname?.includes('/settings')
            : pathname === item.href || (item.href !== '/' && pathname?.startsWith(item.href));
          const Icon = item.icon;
          const href = buildHref(item.href);

          return (
            <Link
              key={item.href}
              href={href}
              className={cn(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

