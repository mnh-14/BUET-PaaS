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
  current_stage?: string;
  status_message?: string;
  failed_stage?: string;
  instance_size?: InstanceSize;
  resources?: DeploymentResources;
  public_url?: string;
  error_summary?: string;
  failure?: DeploymentFailure | null;
  commit_sha?: string;
  security_scan?: SecurityScan;
  deployed_at: string;
}

export interface DeploymentFailure {
  source: "git" | "sonarqube" | "kubernetes" | "backend";
  stage: string;
  title: string;
  summary: string;
  reason?: string;
  suggestion?: string;
  details?: Record<string, unknown>;
}

export interface SecurityScanCondition {
  status: string;
  metric: string;
  comparator?: string | null;
  actual_value?: string | null;
  error_threshold?: string | null;
}

export interface SecurityIssue {
  key?: string | null;
  message: string;
  severity?: string | null;
  type?: string | null;
  rule?: string | null;
  file?: string | null;
  line?: number | null;
}

export interface SecurityScan {
  provider: "sonarqube";
  project_key?: string | null;
  commit_sha?: string | null;
  status: "running" | "passed" | "failed" | "error" | "skipped";
  quality_gate?: string | null;
  analysis_url?: string | null;
  error?: string | null;
  conditions?: SecurityScanCondition[];
  issues?: SecurityIssue[];
  diagnostics?: string[];
}

export type DeploymentStatus =
  | "queued"
  | "cloning"
  | "security_scan_running"
  | "security_scan_passed"
  | "security_scan_failed"
  | "security_scan_error"
  | "build_queued"
  | "build_started"
  | "build_done"
  | "deploy_queued"
  | "deploy_started"
  | "running"
  | "failed"
  | "stopped";

export interface Project {
  project_id: string;
  user_id: string;
  project_name: string;
  repo_url: string;
  instance_size: InstanceSize;
  deploy_branch: string;
  last_deployed_sha?: string | null;
  latest_remote_sha?: string | null;
  last_commit_checked_at?: string | null;
  current_status?: string;
  created_at: string;
  deployments: Deployment[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function apiFetch(url: string, options?: RequestInit): Promise<Response> {
  return fetch(url, { ...options, credentials: "include" });
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

export type InstanceSize = "small" | "medium" | "large";

export interface DeploymentResources {
  replicas: number;
  cpu_request: string;
  cpu_limit: string;
  memory_request: string;
  memory_limit: string;
}

export async function getSession(): Promise<{ user: User }> {
  const res = await apiFetch(`${BASE_URL}/api/v1/session`);
  return handleResponse(res);
}

export async function logoutUser(): Promise<void> {
  const res = await apiFetch(`${BASE_URL}/api/v1/users/logout`, { method: "POST" });
  return handleResponse(res);
}

// ─── Projects ─────────────────────────────────────────────────────────────────

export async function getUserProjects(user_id: string): Promise<Project[]> {
  const res = await apiFetch(`${BASE_URL}/api/v1/users/${user_id}/projects`);
  return handleResponse(res);
}

export async function createProject(data: {
  github_installation_id: number;
  github_repo_id: number;
  deploy_branch: string;
  project_name: string;
  instance_size: InstanceSize;
  env_vars?: Record<string, string>;
}): Promise<{ project_id: string; deployment_id?: string | null; message: string }> {
  const res = await apiFetch(`${BASE_URL}/api/v1/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export interface GitHubInstallation {
  installation_id: number;
  account_login?: string;
  account_type?: string;
  repository_selection?: string;
  status?: string;
  connection_status?: string;
}

export interface GitHubRepository {
  installation_id: number;
  account_login?: string;
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  html_url: string;
}

export interface GitHubBranch {
  name: string;
  sha: string;
}

export async function getGitHubInstallations(): Promise<GitHubInstallation[]> {
  const res = await apiFetch(`${BASE_URL}/api/v1/github/installations`);
  const data = await handleResponse<{ installations: GitHubInstallation[] }>(res);
  return data.installations;
}

export async function getGitHubRepositories(): Promise<GitHubRepository[]> {
  const res = await apiFetch(`${BASE_URL}/api/v1/github/repositories`);
  const data = await handleResponse<{ repositories: GitHubRepository[] }>(res);
  return data.repositories;
}

export async function getGitHubBranches(
  repositoryId: number,
  installationId: number,
): Promise<GitHubBranch[]> {
  const query = new URLSearchParams({ installation_id: String(installationId) });
  const res = await apiFetch(
    `${BASE_URL}/api/v1/github/repositories/${repositoryId}/branches?${query}`,
  );
  const data = await handleResponse<{ branches: GitHubBranch[] }>(res);
  return data.branches;
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
): Promise<{ deployment_id: string; commit_sha: string; message: string }> {
  const res = await apiFetch(
    `${BASE_URL}/api/v1/deployments/redeploy/${project_id}`,
    { method: "POST" }
  );
  return handleResponse(res);
}

export interface UpdateCheck {
  project_id: string;
  branch: string;
  last_deployed_sha?: string | null;
  latest_remote_sha: string;
  update_available: boolean;
  checked_at: string;
}

export async function checkProjectUpdate(projectId: string): Promise<UpdateCheck> {
  const res = await apiFetch(`${BASE_URL}/api/v1/projects/${projectId}/check-update`, {
    method: "POST",
  });
  return handleResponse(res);
}

export function subscribeToDeployment(
  deploymentId: string,
  onUpdate: (deployment: Deployment) => void,
  onError?: () => void,
): EventSource {
  const source = new EventSource(
    `${BASE_URL}/api/v1/deployments/${deploymentId}/events`,
    { withCredentials: true },
  );
  source.onmessage = (event) => onUpdate(JSON.parse(event.data) as Deployment);
  source.onerror = () => onError?.();
  return source;
}
