export interface KeycloakConfig {
  url: string;
  realm: string;
  client: string;
}

export interface PublicConfig {
  keycloak: KeycloakConfig;
}

const cachedConfig: { data: PublicConfig | null; promise: Promise<PublicConfig> | null } = {
  data: null,
  promise: null,
};

export async function fetchPublicConfig(): Promise<PublicConfig> {
  if (cachedConfig.data) {
    return cachedConfig.data;
  }
  if (cachedConfig.promise) {
    return cachedConfig.promise;
  }
  cachedConfig.promise = fetch('/api/v1/config')
    .then((r) => {
      if (!r.ok) throw new Error('Failed to fetch config');
      return r.json();
    })
    .then((data) => {
      cachedConfig.data = data;
      return data;
    })
    .catch((err) => {
      // Do not cache a rejected promise — the next call must be able to retry.
      cachedConfig.promise = null;
      throw err;
    });
  return cachedConfig.promise;
}
