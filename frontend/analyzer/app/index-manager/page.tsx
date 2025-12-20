'use client';

import { useState, useEffect } from 'react';
import { getIndexStatus } from '@/lib/api/client';
import { IndexStatus } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getCurrentUser, requireRole } from '@/lib/auth';

export default function IndexManagerPage() {
  const [indexes, setIndexes] = useState<IndexStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const user = getCurrentUser();

  useEffect(() => {
    // Role check happens in middleware, but double-check here for client-side
    if (!user || !requireRole(user, 'admin')) {
      return;
    }
    getIndexStatus().then((data) => {
      setIndexes(data);
      setLoading(false);
    });
  }, [user]);

  if (!user || !requireRole(user, 'admin')) {
    return (
      <div className="p-6">
        <p className="text-muted-foreground">Unauthorized. Admin access required.</p>
      </div>
    );
  }

  const statusColors = {
    healthy: 'bg-green-500',
    building: 'bg-yellow-500',
    error: 'bg-red-500',
    unknown: 'bg-gray-400',
  };

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Index Manager</h2>
      <p className="text-sm text-muted-foreground mb-6">
        Manage error indexes. Build and refresh indexes as needed.
      </p>
      {loading ? (
        <div className="text-center text-muted-foreground">Loading...</div>
      ) : (
        <div className="grid gap-4">
          {indexes.map((idx) => (
            <Card key={idx.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">{idx.name}</CardTitle>
                  <span className={`w-3 h-3 rounded-full ${statusColors[idx.status]}`} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-muted-foreground mb-4">
                  <div>Status: {idx.status}</div>
                  {idx.lastBuilt && (
                    <div>Last Built: {new Date(idx.lastBuilt).toLocaleString()}</div>
                  )}
                  {idx.machineId && <div>Machine ID: {idx.machineId}</div>}
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" disabled>
                    Build Index
                  </Button>
                  <Button variant="outline" disabled>
                    Refresh
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground mt-2">Not implemented yet</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

