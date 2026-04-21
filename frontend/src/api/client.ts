import axios from 'axios';
import type {
  KBCreate,
  KBUpdate,
  KBDetailResponse,
  KBListResponse,
  DocumentResponse,
  DocumentListResponse,
  ChunkListResponse,
  JobListResponse,
  JobResponse,
  JobRetryResponse,
  SearchDebugRequest,
  SearchDebugResponse,
} from '@/types';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

// ─── Knowledge Base ───

export async function createKB(data: KBCreate) {
  const res = await api.post<KBDetailResponse>('/kb', data);
  return res.data;
}

export async function listKBs(skip = 0, limit = 100) {
  const res = await api.get<KBListResponse>('/kb', { params: { skip, limit } });
  return res.data;
}

export async function getKB(kbId: string) {
  const res = await api.get<KBDetailResponse>(`/kb/${kbId}`);
  return res.data;
}

export async function updateKB(kbId: string, data: KBUpdate) {
  const res = await api.put<KBDetailResponse>(`/kb/${kbId}`, data);
  return res.data;
}

export async function deleteKB(kbId: string) {
  await api.delete(`/kb/${kbId}`);
}

export async function buildIndex(kbId: string) {
  const res = await api.post(`/kb/${kbId}/build`);
  return res.data;
}

// ─── Documents ───

export async function uploadDocument(
  file: File,
  kbId: string,
  docType?: string,
  profile?: string,
) {
  const form = new FormData();
  form.append('file', file);
  form.append('knowledge_base_id', kbId);
  if (docType) form.append('document_type', docType);
  if (profile) form.append('parser_profile', profile);
  const res = await api.post<DocumentResponse>('/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function listDocuments(params?: {
  knowledge_base_id?: string;
  status?: string;
  skip?: number;
  limit?: number;
}) {
  const res = await api.get<DocumentListResponse>('/documents', { params });
  return res.data;
}

export async function getDocument(docId: string) {
  const res = await api.get<DocumentResponse>(`/documents/${docId}`);
  return res.data;
}

export function getDocumentFileUrl(docId: string): string {
  return `/api/documents/${docId}/file`;
}

export async function enableDocument(docId: string) {
  const res = await api.post<DocumentResponse>(`/documents/${docId}/enable`);
  return res.data;
}

export async function disableDocument(docId: string) {
  const res = await api.post<DocumentResponse>(`/documents/${docId}/disable`);
  return res.data;
}

export async function deleteDocument(docId: string) {
  await api.delete(`/documents/${docId}`);
}

export async function getDocumentChunks(
  docId: string,
  skip = 0,
  limit = 50,
) {
  const res = await api.get<ChunkListResponse>(`/documents/${docId}/chunks`, {
    params: { skip, limit },
  });
  return res.data;
}

// ─── Jobs ───

export async function listJobs(params?: {
  status?: string;
  queue_name?: string;
  document_id?: string;
  skip?: number;
  limit?: number;
}) {
  const res = await api.get<JobListResponse>('/jobs', { params });
  return res.data;
}

export async function getJob(jobId: string) {
  const res = await api.get<JobResponse>(`/jobs/${jobId}`);
  return res.data;
}

export async function retryJob(jobId: string) {
  const res = await api.post<JobRetryResponse>(`/jobs/${jobId}/retry`);
  return res.data;
}

// ─── Search ───

export async function searchDebug(kbId: string, body: SearchDebugRequest) {
  const res = await api.post<SearchDebugResponse>(
    `/kb/${kbId}/search_debug`,
    body,
  );
  return res.data;
}
