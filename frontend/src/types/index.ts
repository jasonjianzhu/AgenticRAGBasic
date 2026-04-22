/** TypeScript interfaces matching backend API schemas */

// ─── Knowledge Base ───

export interface KBSettings {
  default_chunker: string;
  default_parser_profile: string;
  embedding_model?: string;
}

export interface KBCreate {
  name: string;
  description?: string;
  settings?: KBSettings;
}

export interface KBUpdate {
  name?: string;
  description?: string;
  settings?: KBSettings;
  is_active?: boolean;
}

export interface KBStatistics {
  document_count: number;
  chunk_count: number;
  ready_doc_count: number;
  failed_doc_count: number;
}

export interface KBResponse {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface KBDetailResponse extends KBResponse {
  statistics: KBStatistics;
}

export interface KBListResponse {
  items: KBResponse[];
  total: number;
}

// ─── Documents ───

export interface DocumentResponse {
  id: string;
  title: string;
  status: string;
  content_hash: string;
  knowledge_base_id: string;
  source_filename: string;
  mime_type: string;
  file_size_bytes: number;
  document_type: string;
  is_enabled: boolean;
  storage_path: string;
  created_at: string;
  updated_at: string;
  job_id: string | null;
}

export interface DocumentListResponse {
  items: DocumentResponse[];
  total: number;
}

export interface ChunkResponse {
  id: string;
  ordinal: number;
  chunk_type: string;
  content: string;
  section_path: string | null;
  page_start: number | null;
  page_end: number | null;
  token_count: number | null;
}

export interface ChunkListResponse {
  items: ChunkResponse[];
  total: number;
}

// ─── Jobs ───

export interface JobResponse {
  id: string;
  rq_job_id: string | null;
  queue_name: string;
  job_type: string;
  status: string;
  document_id: string | null;
  attempts: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface JobListResponse {
  items: JobResponse[];
  total: number;
}

export interface JobRetryResponse {
  id: string;
  status: string;
  attempts: number;
  message: string;
}

// ─── Search ───

export interface SearchFilters {
  document_type?: string;
  language?: string;
  product_model?: string;
}

export interface SearchDebugRequest {
  query: string;
  top_k?: number;
  filters?: SearchFilters;
}

export interface SearchResultItem {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;
  score: number;
  chunk_type: string;
  page_start: number | null;
  page_end: number | null;
  section_path: string | null;
  metadata: Record<string, unknown>;
}

export interface SearchTrace {
  dense_hits: number;
  sparse_hits: number;
  fused_total: number;
  returned: number;
}

export interface SearchDebugResponse {
  query: string;
  results: SearchResultItem[];
  trace: SearchTrace;
}

// ─── RAG ───

export interface RAGSearchFilters {
  document_type?: string;
  language?: string;
  product_model?: string;
}

export interface RAGSearchRequest {
  query: string;
  kb_ids: string[];
  top_k?: number;
  filters?: RAGSearchFilters;
  enable_rewrite?: boolean;
}

export interface RAGSearchResultItem {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;
  score: number;
  rerank_score: number | null;
  chunk_type: string;
  page_start: number | null;
  page_end: number | null;
  section_path: string | null;
  metadata: Record<string, unknown>;
}

export interface RAGSearchTrace {
  query_normalized: string;
  query_rewritten: string | null;
  retrieval_context: Record<string, string>;
  dense_hits: number;
  sparse_hits: number;
  fused_total: number;
  reranked: boolean;
  returned: number;
  latency_ms: Record<string, number>;
}

export interface RAGSearchResponse {
  query: string;
  rewritten_query: string | null;
  results: RAGSearchResultItem[];
  trace: RAGSearchTrace;
}

export interface RAGAnswerRequest {
  query: string;
  kb_ids: string[];
  top_k?: number;
  filters?: RAGSearchFilters;
  enable_rewrite?: boolean;
  enable_rerank?: boolean;
}

export interface SSEEvent {
  event: 'trace' | 'citation' | 'token' | 'done' | 'error';
  data: Record<string, unknown>;
}

export interface Citation {
  index: number;
  document_title: string;
  page: number | null;
  chunk_id: string;
  snippet: string;
}
