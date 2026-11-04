// Backend endpoint, resolved at build time from Vite env files.
// Mode comes from Vite itself (`vite` = development, `vite build` = production,
// or `--mode staging` to load .env.staging) — no separate APP_MODE needed.

const trimSlash = (url: string) => url.replace(/\/+$/, '');

// Empty = same origin as the page (dev proxy, or backend served behind the same host in prod).
export const API_BASE_URL = trimSlash(import.meta.env.VITE_API_URL ?? '');

export const APP_MODE = import.meta.env.MODE;
export const IS_DEV = import.meta.env.DEV;

export const apiUrl = (path: string) => `${API_BASE_URL}${path}`;
