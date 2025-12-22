'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function SettingsPage() {
  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-4">Settings</h2>
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Environment</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-sm">
              <div>
                <span className="font-medium">Base Path:</span>{' '}
                {process.env.NEXT_PUBLIC_BASE_PATH || '(none)'}
              </div>
              <div>
                <span className="font-medium">API URL:</span>{' '}
                {process.env.NEXT_PUBLIC_ANALYZER_API_URL || '(relative)'}
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Preferences</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Settings will be available here (e.g., default group collapsed state)
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

