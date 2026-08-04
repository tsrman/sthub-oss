import api from './api';
import * as T from './types';

export function getApiErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error;
  if (error instanceof Error) {
    const data = (
      error as {
        response?: { data?: { error?: { message?: string }; detail?: string } };
      }
    ).response?.data;
    // Backend uses the {error: {code, message}} envelope; fall back to {detail}.
    return data?.error?.message || data?.detail || error.message || 'An error occurred';
  }
  return 'An error occurred';
}

export const me = () => api.get<T.User>('/me').then((r) => r.data);

export const listApps = (params?: { status?: string; q?: string; owner?: string }) =>
  api.get<T.StreamlitListResponse>('/streamlits', { params }).then((r) => r.data);

export const createApp = (data: T.StreamlitCreate) =>
  api.post<T.StreamlitDetail>('/streamlits', data).then((r) => r.data);

export const getApp = (id: string) =>
  api.get<T.StreamlitDetail>(`/streamlits/${id}`).then((r) => r.data);

export const updateApp = (id: string, data: T.StreamlitUpdate) =>
  api.patch<T.StreamlitDetail>(`/streamlits/${id}`, data).then((r) => r.data);

export const deleteApp = (id: string) => api.delete(`/streamlits/${id}`);

export const runApp = (id: string) =>
  api.post<T.RunResponse>(`/streamlits/${id}/run`).then((r) => r.data);

export const stopApp = (id: string) =>
  api.post<T.RunResponse>(`/streamlits/${id}/stop`).then((r) => r.data);

export const restartApp = (id: string) =>
  api.post<T.RunResponse>(`/streamlits/${id}/restart`).then((r) => r.data);

export const duplicateApp = (id: string) =>
  api.post<T.StreamlitDetail>(`/streamlits/${id}/duplicate`).then((r) => r.data);

export const checkSlug = (slug: string, excludeId?: string) =>
  api
    .get<T.SlugCheckResponse>('/streamlits/check-slug', {
      params: { slug, exclude_id: excludeId },
    })
    .then((r) => r.data);

export const listFiles = (id: string) =>
  api.get<T.StreamlitFilesResponse>(`/streamlits/${id}/files`).then((r) => r.data);

export const getFile = (id: string, path: string, opts?: { base64?: boolean }) =>
  api
    .get<T.StreamlitFileRead>(`/streamlits/${id}/files/${encodeURIComponent(path)}`, {
      params: opts?.base64 ? { base64: 'true' } : undefined,
    })
    .then((r) => r.data);

export const saveFile = (
  id: string,
  path: string,
  data: { content: string; content_type: string }
) =>
  api
    .put<T.StreamlitFileRead>(`/streamlits/${id}/files/${encodeURIComponent(path)}`, data)
    .then((r) => r.data);

export const deleteFile = (id: string, path: string) =>
  api.delete(`/streamlits/${id}/files/${encodeURIComponent(path)}`);

export const lintCode = (id: string, code: string) =>
  api.post<T.LintResponse>(`/streamlits/${id}/lint`, { code }).then((r) => r.data);

export const listDeployments = () =>
  api.get<T.DeploymentListResponse>('/deployments').then((r) => r.data);

export const aiStatus = () => api.get<T.AiStatus>('/ai/status').then((r) => r.data);
