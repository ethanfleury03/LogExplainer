'use client';

import { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { User, IndexStatus } from '@/lib/types';
import { getIndexStatus } from '@/lib/api/client';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { User as UserIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface TopBarProps {
  user: User | null;
  selectedIndex: string;
  onIndexChange: (indexId: string) => void;
}

const statusColors = {
  healthy: 'bg-green-500',
  building: 'bg-yellow-500',
  error: 'bg-red-500',
  unknown: 'bg-gray-400',
};

export function TopBar({ user, selectedIndex, onIndexChange }: TopBarProps) {
  const pathname = usePathname();
  const [indexes, setIndexes] = useState<IndexStatus[]>([]);
  const [loading, setLoading] = useState(true);

  // Hide Machine/Index dropdown on Error Debug pages
  const isErrorDebugPage = pathname?.startsWith('/tech/error-debug') || false;

  useEffect(() => {
    if (!isErrorDebugPage) {
      getIndexStatus().then((data) => {
        setIndexes(data);
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, [isErrorDebugPage]);

  const currentIndex = indexes.find((idx) => idx.id === selectedIndex) || indexes[0];
  const roleBadgeColor = user?.role === 'admin' ? 'bg-purple-500' : user?.role === 'tech' ? 'bg-blue-500' : 'bg-gray-500';

  return (
    <div className="h-16 border-b bg-white flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-semibold">{isErrorDebugPage ? 'Error Debug' : 'Error Analyzer'}</h1>
        {!isErrorDebugPage && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Machine/Index:</span>
            <Select value={selectedIndex} onValueChange={onIndexChange} disabled={loading}>
              <SelectTrigger className="w-[200px]">
                <SelectValue>
                  {currentIndex ? (
                    <div className="flex items-center gap-2">
                      <span className={cn('w-2 h-2 rounded-full', statusColors[currentIndex.status])} />
                      {currentIndex.name}
                    </div>
                  ) : (
                    'Loading...'
                  )}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {indexes.map((idx) => (
                  <SelectItem key={idx.id} value={idx.id}>
                    <div className="flex items-center gap-2">
                      <span className={cn('w-2 h-2 rounded-full', statusColors[idx.status])} />
                      {idx.name}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        {user && (
          <>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">{user.name}</span>
              <span className={cn('px-2 py-1 rounded text-xs text-white font-medium', roleBadgeColor)}>
                {user.role.toUpperCase()}
              </span>
            </div>
            <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
              <UserIcon className="h-4 w-4" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

