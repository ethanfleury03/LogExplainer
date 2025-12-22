'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { emailIngestScript } from '@/lib/api/error-debug-client';

export default function SettingsPage() {
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailSuccess, setEmailSuccess] = useState<string | null>(null);

  const handleEmailScript = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setEmailError('Please enter an email address');
      return;
    }

    setSending(true);
    setEmailError(null);
    setEmailSuccess(null);

    try {
      const result = await emailIngestScript(email.trim());
      setEmailSuccess(`Email sent successfully to ${result.to}`);
      setEmail('');
      setTimeout(() => {
        setShowEmailModal(false);
        setEmailSuccess(null);
      }, 2000);
    } catch (err: any) {
      setEmailError(err.message || 'Failed to send email. Please check backend configuration.');
    } finally {
      setSending(false);
    }
  };

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
        <Card>
          <CardHeader>
            <CardTitle>Index</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Email the index script (ingest.py) to a technician. The script can be run on a printer
              to generate an index file that can be uploaded to the Error Debug system.
            </p>
            <Button onClick={() => setShowEmailModal(true)}>Email Index Script</Button>
          </CardContent>
        </Card>
      </div>

      {showEmailModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <Card className="p-6 w-full max-w-md">
            <h2 className="text-xl font-bold mb-4">Email Index Script</h2>
            <form onSubmit={handleEmailScript}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-1">Email Address *</label>
                <input
                  type="email"
                  required
                  className="w-full border rounded px-3 py-2"
                  placeholder="technician@example.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setEmailError(null);
                    setEmailSuccess(null);
                  }}
                  disabled={sending}
                />
              </div>
              {emailError && (
                <div className="mb-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded text-sm">
                  {emailError}
                </div>
              )}
              {emailSuccess && (
                <div className="mb-4 bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded text-sm">
                  {emailSuccess}
                </div>
              )}
              <div className="flex gap-2 justify-end">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowEmailModal(false);
                    setEmail('');
                    setEmailError(null);
                    setEmailSuccess(null);
                  }}
                  disabled={sending}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={sending}>
                  {sending ? 'Sending...' : 'Send Email'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}

