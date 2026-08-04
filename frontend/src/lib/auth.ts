import Keycloak from 'keycloak-js';
import { fetchPublicConfig } from './config';

interface InitOptions {
  onLoad?: 'check-sso' | 'login-required';
}

const KEYCLOAK_GLOBAL_KEY = '__sthubKeycloak';

declare global {
  interface Window {
    [KEYCLOAK_GLOBAL_KEY]?: Keycloak;
  }
}

export function getStoredKeycloak(): Keycloak | null {
  if (typeof window === 'undefined') return null;
  return window[KEYCLOAK_GLOBAL_KEY] || null;
}

function setStoredKeycloak(kc: Keycloak): void {
  if (typeof window !== 'undefined') {
    window[KEYCLOAK_GLOBAL_KEY] = kc;
  }
}

export function clearStoredKeycloak(): void {
  if (typeof window !== 'undefined') {
    delete window[KEYCLOAK_GLOBAL_KEY];
  }
}

function isInitialized(kc: Keycloak): boolean {
  return Boolean((kc as unknown as Record<string, boolean>).__sthubInitialized);
}

function markInitialized(kc: Keycloak): void {
  (kc as unknown as Record<string, boolean>).__sthubInitialized = true;
}

function isInitializing(kc: Keycloak): boolean {
  return Boolean((kc as unknown as Record<string, Promise<Keycloak> | undefined>).__sthubInitPromise);
}

function getInitPromise(kc: Keycloak): Promise<Keycloak> | undefined {
  return (kc as unknown as Record<string, Promise<Keycloak> | undefined>).__sthubInitPromise;
}

function setInitPromise(kc: Keycloak, promise: Promise<Keycloak> | undefined): void {
  (kc as unknown as Record<string, Promise<Keycloak> | undefined>).__sthubInitPromise = promise;
}

export async function initKeycloak(options: InitOptions = {}, force = false) {
  if (!force) {
    const stored = getStoredKeycloak();
    if (stored) {
      if (stored.authenticated || isInitialized(stored)) {
        return stored;
      }
      const pending = getInitPromise(stored);
      if (pending) {
        return pending;
      }
    }
  }

  const cfg = await fetchPublicConfig();
  const kc = new Keycloak({
    url: cfg.keycloak.url,
    realm: cfg.keycloak.realm,
    clientId: cfg.keycloak.client,
  });
  setStoredKeycloak(kc);

  const initOpts: Keycloak.KeycloakInitOptions = {
    pkceMethod: 'S256',
    silentCheckSsoRedirectUri:
      typeof window !== 'undefined' ? window.location.origin + '/callback' : undefined,
  };
  if (options.onLoad) {
    initOpts.onLoad = options.onLoad;
  }

  const promise = kc.init(initOpts).then(() => {
    markInitialized(kc);
    setInitPromise(kc, undefined);
    return kc;
  });
  setInitPromise(kc, promise);
  return promise;
}

export function getKeycloak() {
  const kc = getStoredKeycloak();
  if (!kc) throw new Error('Keycloak not initialized');
  return kc;
}

export async function doLogin() {
  const kc = await initKeycloak({}, true);
  await kc.login({
    redirectUri: typeof window !== 'undefined' ? window.location.origin + '/callback' : '/callback',
  });
}

export async function doLogout() {
  const kc = await initKeycloak();
  await kc.logout({ redirectUri: typeof window !== 'undefined' ? window.location.origin : '/' });
}

export async function getToken() {
  const kc = getStoredKeycloak();
  if (kc && kc.authenticated) {
    await kc.updateToken(30);
    return kc.token || '';
  }
  return '';
}
