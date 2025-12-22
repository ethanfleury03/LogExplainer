'use client';

import { useState, useEffect } from 'react';
import { User } from '@/lib/types';
import { getCurrentUser } from '@/lib/auth';
import { TopBar } from './TopBar';
import { Sidebar } from './Sidebar';
import { MachineSidebar } from './MachineSidebar';

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const [user, setUser] = useState<User | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<string>('all');

  useEffect(() => {
    setUser(getCurrentUser());
  }, []);

  return (
    <div className="h-screen flex flex-col">
      <TopBar user={user} selectedIndex={selectedIndex} onIndexChange={setSelectedIndex} />
      <div className="flex-1 flex overflow-hidden">
        <MachineSidebar user={user} />
        <Sidebar user={user} />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}

