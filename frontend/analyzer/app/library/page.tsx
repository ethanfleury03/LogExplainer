'use client';

import { useState, useEffect } from 'react';
import { listErrorKeys } from '@/lib/api/client';
import { ErrorKey } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function LibraryPage() {
  const [errorKeys, setErrorKeys] = useState<ErrorKey[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listErrorKeys().then((data) => {
      setErrorKeys(data);
      setLoading(false);
    });
  }, []);

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Error Library</h2>
      {loading ? (
        <div className="text-center text-muted-foreground">Loading...</div>
      ) : (
        <div className="grid gap-4">
          {errorKeys.map((ek) => (
            <Card key={ek.id}>
              <CardHeader>
                <CardTitle className="text-base">{ek.key}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-sm text-muted-foreground">
                  <div>Occurrences: {ek.occurrenceCount}</div>
                  <div>Last Indexed: {new Date(ek.lastIndexed).toLocaleString()}</div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

