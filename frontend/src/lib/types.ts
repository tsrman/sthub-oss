export interface User {
  login: string;
  display_name: string;
  email: string;
  group: string;
  is_admin: boolean;
}

export type AppStatus = 'stopped' | 'building' | 'running' | 'error';

export interface StreamlitOwner {
  login: string;
  display_name: string;
}

export interface StreamlitApp {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  status: AppStatus;
  cpu_limit: number;
  memory_limit_mb: number;
  python_version: string;
  url: string;
  public_url: string;
  version: number;
  owner: StreamlitOwner;
  created_at: string;
  updated_at: string;
}

export interface StreamlitDetail extends StreamlitApp {
  container_id: string | null;
  image_tag: string | null;
}

export interface StreamlitCreate {
  name: string;
  slug: string;
  description?: string | null;
  python_version?: string;
  cpu_limit?: number;
  memory_limit_mb?: number;
}

export type StreamlitUpdate = Partial<StreamlitCreate>;

export interface RunResponse {
  id: string;
  status: AppStatus;
  version: number;
}

export interface SlugCheckResponse {
  slug: string;
  normalized: string;
  available: boolean;
  url: string;
}

export interface StreamlitFileSummary {
  path: string;
  content_type: string;
  size: number;
  is_entrypoint: boolean;
  updated_at: string;
}

export interface StreamlitFileRead {
  path: string;
  content_type: string;
  content: string;
  is_entrypoint: boolean;
}

export interface StreamlitFilesResponse {
  items: StreamlitFileSummary[];
}

export interface StreamlitListResponse {
  items: StreamlitApp[];
  total: number;
  running: number;
}

export interface LintError {
  line: number;
  column: number;
  severity: 'error' | 'warning';
  message: string;
  code: string;
}

export interface LintResponse {
  ok: boolean;
  problems: LintError[];
}

export interface DeploymentActor {
  login: string;
  display_name: string;
}

export interface Deployment {
  id: string;
  ts: string;
  kind: string;
  version: number;
  result: string;
  streamlit_name: string;
  streamlit_slug: string;
  actor: DeploymentActor;
}

export interface DeploymentListResponse {
  items: Deployment[];
}

export interface AiStatus {
  enabled: boolean;
  model: string;
}

export interface AiChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AiFileContext {
  path: string;
  language: string;
  content: string;
}
