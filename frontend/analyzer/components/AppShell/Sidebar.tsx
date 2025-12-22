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
  { href: '/settings', label: 'Settings', icon: Settings, roles: ['ADMIN', 'TECHNICIAN'] as const },
];

export function Sidebar({ user }: SidebarProps) {
  const pathname = usePathname();

  return (
    <div className="w-64 border-r bg-muted/30 h-full flex flex-col">
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map((item) => {
          if (!user || !item.roles.some((role) => hasRole(user, role))) {
            return null;
          }

          const isActive = pathname === item.href || (item.href !== '/' && pathname?.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
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

