/** Agent-related TypeScript interfaces */

// ─── SSE Events ───

export type AgentSSEEventType =
  | 'token'
  | 'tool_start'
  | 'tool_result'
  | 'citation'
  | 'data_table'
  | 'chart'
  | 'trace'
  | 'done'
  | 'error';

export interface AgentSSEEvent {
  event: AgentSSEEventType;
  data: Record<string, unknown>;
}

// ─── Tool Events ───

export interface ToolStartEvent {
  tool: string;
  args_summary: string;
}

export interface ToolResultEvent {
  tool: string;
  summary: string;
}

// ─── Data Table ───

export interface DataTableEvent {
  columns: string[];
  rows: unknown[][];
  row_count: number;
}

// ─── Chart ───

export interface ChartEvent {
  title?: { text: string };
  tooltip?: Record<string, unknown>;
  legend?: Record<string, unknown>;
  xAxis?: Record<string, unknown>;
  yAxis?: Record<string, unknown>;
  series?: Record<string, unknown>[];
  // pie charts
  chart_type?: string;
  columns?: string[];
  rows?: unknown[][];
}

// ─── Citation ───

export interface AgentCitation {
  index: number;
  document_title: string;
  page: number | null;
  snippet: string;
}

// ─── Sessions ───

export interface SessionItem {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SessionListResponse {
  items: SessionItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface SessionMessage {
  id: string;
  role: string;
  content: string;
  message_type: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_result?: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface SessionDetailResponse {
  id: string;
  title: string;
  status: string;
  messages: SessionMessage[];
  created_at: string;
  updated_at: string;
}

// ─── Chat Request ───

export interface AgentChatRequest {
  session_id?: string;
  message: string;
  kb_ids?: string[];
}

// ─── Message for UI rendering ───

export interface AgentMessage {
  role: 'user' | 'assistant';
  content: string;
  loading?: boolean;
  error?: string;
  toolCalls?: ToolCallInfo[];
  citations?: AgentCitation[];
  dataTables?: DataTableEvent[];
  charts?: ChartEvent[];
}

export interface ToolCallInfo {
  tool: string;
  argsSummary: string;
  result?: string;
  status: 'running' | 'done' | 'error';
}
