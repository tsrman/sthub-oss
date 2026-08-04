import axios from 'axios';
import { getStoredKeycloak, clearStoredKeycloak } from './auth';

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api/v1',
  headers: { 'Content-Type': 'application/json' },
});

export function setAuthToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

api.interceptors.request.use(
  async (config) => {
    if (typeof window === 'undefined') return config;
    const kc = getStoredKeycloak();
    if (kc && kc.authenticated) {
      await kc.updateToken(30);
      config.headers.Authorization = `Bearer ${kc.token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (typeof window === 'undefined') return Promise.reject(error);

    const status = error.response?.status;
    const data = error.response?.data;

    if (status === 401) {
      // Session expired mid-flight (e.g. refresh token gone): drop the stale
      // Keycloak instance and bounce to login, unless we are already there.
      clearStoredKeycloak();
      setAuthToken(null);
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    } else if (status === 403) {
      const message = data?.error?.message || data?.detail || 'Access denied';
      window.alert(message);
    } else if (status === 409 && data?.error?.code === 'quota_exceeded') {
      const message = data?.error?.message || 'Quota exceeded';
      window.alert(message);
    }

    return Promise.reject(error);
  }
);

export default api;
