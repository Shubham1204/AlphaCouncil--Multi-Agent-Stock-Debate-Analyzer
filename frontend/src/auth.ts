// Optional OIDC token acquisition for the frontend.
//
// The backend gates on an OIDC id_token when REQUIRE_AUTH=true. This module
// obtains that token, trying (in order):
//   1. VITE_AUTH_TOKEN — a build/dev-time token for local testing.
//   2. A token captured from a prior OIDC redirect (sessionStorage).
//   3. null — no auth (local/mock backend with REQUIRE_AUTH off).
//
// For a full production login, wire beginSso() to your OIDC provider
// (Cognito, Auth0, Okta, Google, Entra ID, ...): set VITE_OIDC_AUTH_URL and
// VITE_OIDC_CLIENT_ID. Returns null when no token is available; callers then
// rely on the backend being in no-auth mode.

const env = (import.meta as any).env || {};

export async function getAuthToken(): Promise<string | null> {
  // 1. Explicit dev/build token.
  if (env.VITE_AUTH_TOKEN) return env.VITE_AUTH_TOKEN as string;

  // 2. Token captured from a prior SSO redirect (stored in sessionStorage).
  const cached = sessionStorage.getItem("auth_id_token");
  if (cached) return cached;

  // 3. No auth configured.
  return null;
}

// Kick off an OIDC redirect to obtain an id_token, if configured. Call this
// when a request 401s and no token is available. On return, the token is in the
// URL fragment; capture it and stash it in sessionStorage.
export function beginSso(): boolean {
  const authUrl = env.VITE_OIDC_AUTH_URL;
  const clientId = env.VITE_OIDC_CLIENT_ID;
  if (!authUrl || !clientId) return false;
  const redirect = env.VITE_OIDC_REDIRECT_URI || window.location.origin;
  const nonce = (crypto as any).randomUUID
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
  sessionStorage.setItem("oidc_nonce", nonce);
  window.location.href =
    `${authUrl}?response_type=id_token` +
    `&client_id=${encodeURIComponent(clientId)}` +
    `&redirect_uri=${encodeURIComponent(redirect)}` +
    `&scope=openid&nonce=${nonce}`;
  return true;
}

// Call once on app load to capture a token returned in the URL fragment
// (#id_token=...) after an OIDC implicit-flow redirect.
export function captureSsoFragment() {
  if (!window.location.hash) return;
  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get("id_token");
  if (token) {
    sessionStorage.setItem("auth_id_token", token);
    history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}
