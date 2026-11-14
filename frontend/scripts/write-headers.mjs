// Runs after `vite build`. Writes dist/_headers, which Cloudflare Pages uses
// to send security headers with every page.
//
// The Content-Security-Policy only lets the page load its own files and talk
// to our own backend (VITE_SERVER_URL), so injected scripts cannot run or send
// data anywhere else.
import { readFileSync, writeFileSync, existsSync } from "node:fs";

function serverUrl() {
  if (process.env.VITE_SERVER_URL) return process.env.VITE_SERVER_URL;
  for (const file of [".env.production.local", ".env.production", ".env.local", ".env"]) {
    if (!existsSync(file)) continue;
    const m = readFileSync(file, "utf8").match(/^VITE_SERVER_URL=(.*)$/m);
    if (m && m[1].trim()) return m[1].trim();
  }
  return "";
}

const api = serverUrl();
let connect = "'self'";
if (api) {
  const u = new URL(api);
  connect += ` ${u.origin} ${u.protocol === "https:" ? "wss:" : "ws:"}//${u.host}`;
} else {
  console.warn("write-headers: VITE_SERVER_URL is not set; sockets are only allowed to this site.");
}

const csp = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "img-src 'self' data:",
  `connect-src ${connect}`,
  "font-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "upgrade-insecure-requests",
].join("; ");

const headers = `/*
  Content-Security-Policy: ${csp}
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
  Cross-Origin-Opener-Policy: same-origin

/assets/*
  Cache-Control: public, max-age=31536000, immutable

/index.html
  Cache-Control: no-cache
`;

writeFileSync("dist/_headers", headers);
console.log("write-headers: dist/_headers written" + (api ? ` (backend ${new URL(api).host})` : ""));
