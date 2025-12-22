'use client';

import { useState, useEffect } from 'react';
import { OccurrenceDetail } from '@/lib/types';
import { getOccurrenceDetail } from '@/lib/api/client';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Copy } from 'lucide-react';

interface DetailsPaneProps {
  occurrenceId: string | null;
}

export function DetailsPane({ occurrenceId }: DetailsPaneProps) {
  const [detail, setDetail] = useState<OccurrenceDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!occurrenceId) {
      setDetail(null);
      return;
    }

    setLoading(true);
    getOccurrenceDetail(occurrenceId)
      .then((data) => {
        setDetail(data);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, [occurrenceId]);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    // TODO: Add toast notification
  };

  if (!occurrenceId) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground bg-muted/30">
        Select an occurrence to view details
      </div>
    );
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground">
        Loading...
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="h-full flex items-center justify-center text-muted-foreground">
        Error loading details
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col border-l bg-white">
      <div className="border-b p-4">
        <h3 className="font-semibold">{detail.errorKey}</h3>
        <p className="text-sm text-muted-foreground">
          {detail.filePath}:{detail.lineNumber}
        </p>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <Tabs defaultValue="summary" className="w-full">
          <TabsList>
            <TabsTrigger value="summary">Summary</TabsTrigger>
            <TabsTrigger value="function">Function</TabsTrigger>
            <TabsTrigger value="code">Code</TabsTrigger>
            <TabsTrigger value="metadata">Metadata</TabsTrigger>
            <TabsTrigger value="raw">Raw</TabsTrigger>
          </TabsList>

          <TabsContent value="summary" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Summary</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">{detail.summary || 'No summary available'}</p>
                <div className="mt-4 space-y-2">
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">Confidence:</span>
                    <span className="ml-2">{(detail.confidence * 100).toFixed(0)}%</span>
                  </div>
                  {detail.functionName && (
                    <div>
                      <span className="text-xs font-medium text-muted-foreground">Function:</span>
                      <span className="ml-2 font-mono">{detail.functionName}</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="function" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Function Context</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute top-2 right-2"
                    onClick={() => handleCopy(detail.context)}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  <pre className="text-xs font-mono bg-muted p-3 rounded overflow-auto">
                    {detail.context}
                  </pre>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="code" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Full Code</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute top-2 right-2"
                    onClick={() => handleCopy(detail.fullCode || detail.context)}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  <pre className="text-xs font-mono bg-muted p-3 rounded overflow-auto">
                    {detail.fullCode || detail.context}
                  </pre>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="metadata" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Metadata</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {detail.metadata ? (
                    Object.entries(detail.metadata).map(([key, value]) => (
                      <div key={key} className="flex">
                        <span className="text-xs font-medium text-muted-foreground w-32">{key}:</span>
                        <span className="text-xs">{value}</span>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-muted-foreground">No metadata available</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="raw" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Raw JSON</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="relative">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute top-2 right-2"
                    onClick={() => handleCopy(JSON.stringify(detail, null, 2))}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                  <pre className="text-xs font-mono bg-muted p-3 rounded overflow-auto">
                    {JSON.stringify(detail, null, 2)}
                  </pre>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

