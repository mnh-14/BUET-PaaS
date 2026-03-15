const BASE_URL = "";

export { BASE_URL };

// ─── Types ────────────────────────────────────────────────────────────────────

export interface User {
  user_id: string;
  name: string;
  email: string;
  credit_balance: number;
  created_at: string;
}

export interface Deployment {
  deployment_id: string;
  project_id: string;
  status: DeploymentStatus;
  port?: number;
  public_url?: string;
  error_summary?: string;
  deployed_at: string;
}

export type DeploymentStatus =
  | "queued"
  | "cloning"
  | "building"
  | "starting"
  | "running"
  | "failed"
  | "stopped";

export interface Project {
  project_id: string;
  user_id: string;
  project_name: string;
  repo_url: string;
  created_at: string;
  deployments: Deployment[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function apiFetch(url: string, options?: RequestInit): Promise<Response> {
  return fetch(url, options);
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export async function registerUser(data: {
  user_id: string;
  name: string;
  email: string;
  password: string;
}): Promise<{ message: string }> {
  const res = await apiFetch(`${BASE_URL}/api/v1/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function loginUser(data: {
  user_id: string;
  password: string;
}): Promise<{ user: User }> {
  const res = await apiFetch(`${BASE_URL}/api/v1/users/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export async function getUserProjects(user_id: string): Promise<Project[]> {
  const res = await apiFetch(`${BASE_URL}/api/v1/users/${user_id}/projects`);
  return handleResponse(res);
}

export async function createProject(data: {
  repo_url: string;
  user_id: string;
  project_name: string;
}): Promise<{ project_id: string; deployment_id: string; message: string }> {
  const res = await apiFetch(`${BASE_URL}/api/v1/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function getProject(project_id: string): Promise<Project> {
  const res = await apiFetch(`${BASE_URL}/api/v1/projects/${project_id}`);
  return handleResponse(res);
}

export async function deleteProject(project_id: string): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/api/v1/projects/${project_id}`, {
    method: "DELETE",
  });
  return handleResponse(res);
}

// ─── Deployments ─────────────────────────────────────────────────────────────

export async function getDeployment(deployment_id: string): Promise<Deployment> {
  const res = await apiFetch(`${BASE_URL}/api/v1/deployments/${deployment_id}`);
  return handleResponse(res);
}

export async function redeployProject(
  project_id: string
): Promise<{ deployment_id: string; message: string }> {
  const res = await apiFetch(
    `${BASE_URL}/api/v1/deployments/redeploy/${project_id}`,
    { method: "POST" }
  );
  return handleResponse(res);
}
