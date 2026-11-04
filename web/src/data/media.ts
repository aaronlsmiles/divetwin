// Where clips.json, the mp4s and the PNG atlases come from. The page never knows which host: Phase 6 decides.
//   dev        the Vite middleware (vite/media-dev.ts) serves runs/assets at /media/
//   production VITE_MEDIA_BASE, set at build time to the media host's divetwin/v1/ prefix (Phase 6, on Aaron's word)
// A production build with the variable unset has no media; the page says so rather than guessing a host.
export interface MediaEnv { DEV: boolean; VITE_MEDIA_BASE?: string }

export function resolveBase(env: MediaEnv): string {
  const set = env.VITE_MEDIA_BASE;
  if (set) return set.endsWith("/") ? set : `${set}/`;
  return env.DEV ? "/media/" : "";
}

export const mediaBase = (): string => resolveBase(import.meta.env as unknown as MediaEnv);
export const hasMedia = (base: string = mediaBase()): boolean => base !== "";
export const mediaUrl = (path: string, base: string = mediaBase()): string => base + path.replace(/^\/+/, "");
