export type Health = {
  status: "ok" | "degraded";
  version: string;
  git_sha: string;
  environment: string;
  database: "ok" | "unavailable";
};

export type Me = { name: string | null; authenticated: boolean };

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(path, { headers: { Accept: "application/json" } });
  // /api/health answers 503 with a body when the database is down; still parse it.
  if (!resp.ok && resp.status !== 503) {
    throw new Error(`${path} failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export const fetchHealth = () => getJson<Health>("/api/health");
export const fetchMe = () => getJson<Me>("/api/me");
