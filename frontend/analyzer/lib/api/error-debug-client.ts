/**
 * API client for Error Debug feature.
 */

import { getCurrentUser } from '../auth';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface Machine {
  id: string;
  display_name: string;
  printer_model: string;
  printing_type: string;
  created_at: string;
  updated_at: string;
  active_version?: {
    id: string;
    indexed_at: string;
    total_chunks: number;
    total_errors: number;
    schema_version: string;
  };
}

interface MachineVersion {
  id: string;
  created_at: string;
  indexed_at: string;
  schema_version: string;
  is_active: boolean;
  total_chunks: number;
  total_errors: number;
  stats: Record<string, any>;
}

interface SearchResult {
  error_key: string;
  chunks: Array<{
    chunk_id: string;
    function_name: string;
    class_name?: string;
    file_path: string;
    line_start: number;
    line_end: number;
    signature: string;
    code: string;
    docstring?: string;
    leading_comment?: string;
    error_messages: Array<{
      message: string;
      log_level: string;
      source_type: string;
    }>;
    log_levels: string[];
  }>;
  match_type: 'exact' | 'partial';
  score: number;
}

async function getHeaders(): Promise<HeadersInit> {
  const user = getCurrentUser();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  
  // Dev mode: always add role headers for local testing
  // In production, these would come from session/JWT
  const isDev = process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === 'true' || 
                process.env.NODE_ENV !== 'production';
  
  if (isDev) {
    // Always include role headers in dev mode
    const role = user?.role || 'TECHNICIAN';
    const email = user?.email || 'dev@example.com';
    headers['X-DEV-ROLE'] = role;
    headers['X-DEV-USER'] = email;
  }
  
  return headers;
}

export async function listMachines(): Promise<Machine[]> {
  const url = `${API_BASE_URL}/api/error-debug/machines`;
  const headers = await getHeaders();
  
  console.log('listMachines: Requesting', url, 'with headers', Object.keys(headers));
  
  try {
    const response = await fetch(url, {
      headers,
    });
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('listMachines: Response not OK', response.status, errorText);
      throw new Error(`Failed to list machines: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json();
    console.log('listMachines: Success', data.length, 'machines');
    return data;
  } catch (err: any) {
    console.error('listMachines: Fetch error', err);
    // Re-throw with more context
    if (err.name === 'TypeError' && err.message.includes('fetch')) {
      throw new Error(`Network error: Cannot connect to ${API_BASE_URL}. Is the backend running?`);
    }
    throw err;
  }
}

export async function createMachine(data: {
  display_name: string;
  printer_model: string;
  printing_type: string;
}): Promise<Machine> {
  const formData = new FormData();
  formData.append('display_name', data.display_name);
  formData.append('printer_model', data.printer_model);
  formData.append('printing_type', data.printing_type);
  
  const headers = await getHeaders();
  delete headers['Content-Type']; // Let browser set multipart boundary
  
  const response = await fetch(`${API_BASE_URL}/api/error-debug/machines`, {
    method: 'POST',
    headers,
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to create machine: ${response.statusText}`);
  }
  
  return response.json();
}

export async function updateMachine(
  machineId: string,
  data: {
    display_name?: string;
    printer_model?: string;
    printing_type?: string;
  }
): Promise<Machine> {
  const formData = new FormData();
  if (data.display_name) formData.append('display_name', data.display_name);
  if (data.printer_model) formData.append('printer_model', data.printer_model);
  if (data.printing_type) formData.append('printing_type', data.printing_type);
  
  const headers = await getHeaders();
  delete headers['Content-Type'];
  
  const response = await fetch(`${API_BASE_URL}/api/error-debug/machines/${machineId}`, {
    method: 'PUT',
    headers,
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to update machine: ${response.statusText}`);
  }
  
  return response.json();
}

export async function deleteMachine(machineId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/error-debug/machines/${machineId}`, {
    method: 'DELETE',
    headers: await getHeaders(),
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to delete machine: ${response.statusText}`);
  }
}

export async function listVersions(machineId: string): Promise<MachineVersion[]> {
  const response = await fetch(`${API_BASE_URL}/api/error-debug/machines/${machineId}/versions`, {
    headers: await getHeaders(),
  });
  
  if (!response.ok) {
    throw new Error(`Failed to list versions: ${response.statusText}`);
  }
  
  return response.json();
}

export async function uploadVersion(
  machineId: string,
  file: File
): Promise<MachineVersion> {
  const formData = new FormData();
  formData.append('file', file);
  
  const headers = await getHeaders();
  delete headers['Content-Type'];
  
  const response = await fetch(`${API_BASE_URL}/api/error-debug/machines/${machineId}/versions`, {
    method: 'POST',
    headers,
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to upload version: ${response.statusText}`);
  }
  
  return response.json();
}

export async function activateVersion(
  machineId: string,
  versionId: string
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/error-debug/machines/${machineId}/versions/${versionId}/activate`,
    {
      method: 'POST',
      headers: await getHeaders(),
    }
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to activate version: ${response.statusText}`);
  }
}

export async function deleteVersion(
  machineId: string,
  versionId: string
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/error-debug/machines/${machineId}/versions/${versionId}`,
    {
      method: 'DELETE',
      headers: await getHeaders(),
    }
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to delete version: ${response.statusText}`);
  }
}

export async function downloadVersion(
  machineId: string,
  versionId: string
): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/api/error-debug/machines/${machineId}/versions/${versionId}/download`,
    {
      headers: await getHeaders(),
    }
  );
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to download version: ${response.statusText}`);
  }
  
  return response.blob();
}

export async function searchIndex(
  machineId: string,
  queryText: string
): Promise<{
  machine_id: string;
  query: string;
  results: SearchResult[];
  total_matches: number;
}> {
  const formData = new FormData();
  formData.append('machine_id', machineId);
  formData.append('query_text', queryText);
  
  const headers = await getHeaders();
  delete headers['Content-Type'];
  
  const response = await fetch(`${API_BASE_URL}/api/error-debug/search`, {
    method: 'POST',
    headers,
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to search: ${response.statusText}`);
  }
  
  return response.json();
}

export async function emailIngestScript(email: string): Promise<{ message: string; to: string }> {
  const formData = new FormData();
  formData.append('email', email);
  
  const headers = await getHeaders();
  delete headers['Content-Type'];
  
  const response = await fetch(`${API_BASE_URL}/api/error-debug/email-ingest`, {
    method: 'POST',
    headers,
    body: formData,
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `Failed to send email: ${response.statusText}`);
  }
  
  return response.json();
}

