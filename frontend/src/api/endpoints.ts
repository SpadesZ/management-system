// File Path: frontend/src/api/endpoints.ts
// Timestamp: 2026-05-26T21:20:00+08:00
// Version: v0.4

import http from "./http";

export const api = {
  login: (email: string, password: string) => http.post("/auth/login", { email, password }),
  registerOptions: () => http.get("/auth/register/options"),
  registerAccount: (payload: Record<string, unknown>) => http.post("/auth/register", payload),
  me: () => http.get("/me"),
  myAssets: (params: Record<string, unknown>) => http.get("/my/assets", { params }),
  myRequests: (params: Record<string, unknown>) => http.get("/my/requests", { params }),
  myOutputs: (params: Record<string, unknown>) => http.get("/my/outputs", { params }),
  dashboardSummary: () => http.get("/dashboard/summary"),
  dashboardAlerts: () => http.get("/dashboard/alerts"),

  users: (params: Record<string, unknown>) => http.get("/users", { params }),
  departments: (params: Record<string, unknown>) => http.get("/departments", { params }),
  projects: (params: Record<string, unknown>) => http.get("/projects", { params }),
  apiKeys: (params: Record<string, unknown>) => http.get("/api-keys", { params }),
  aiAccounts: (params: Record<string, unknown>) => http.get("/ai-accounts", { params }),
  aiAccountCredentials: (accountId: number, params: Record<string, unknown>) =>
    http.get(`/ai-accounts/${accountId}/credentials`, { params }),
  createAiAccountCredential: (accountId: number, payload: Record<string, unknown>) =>
    http.post(`/ai-accounts/${accountId}/credentials`, payload),
  rotateAiAccountCredential: (accountId: number, credentialId: number, payload: Record<string, unknown>) =>
    http.post(`/ai-accounts/${accountId}/credentials/${credentialId}/rotate`, payload),
  disableAiAccountCredential: (accountId: number, credentialId: number) =>
    http.post(`/ai-accounts/${accountId}/credentials/${credentialId}/disable`),
  aiAccountAccessGrants: (accountId: number, params: Record<string, unknown>) =>
    http.get(`/ai-accounts/${accountId}/access-grants`, { params }),
  createAiAccountAccessGrant: (accountId: number, payload: Record<string, unknown>) =>
    http.post(`/ai-accounts/${accountId}/access-grants`, payload),
  revokeAiAccountAccessGrant: (accountId: number, grantId: number, payload: Record<string, unknown>) =>
    http.post(`/ai-accounts/${accountId}/access-grants/${grantId}/revoke`, payload),
  aiAccountHistory: (accountId: number, params: Record<string, unknown>) =>
    http.get(`/ai-accounts/${accountId}/history`, { params }),
  assetContracts: (params: Record<string, unknown>) => http.get("/asset-contracts", { params }),
  createAssetContract: (payload: Record<string, unknown>) => http.post("/asset-contracts", payload),
  patchAssetContract: (contractId: number, payload: Record<string, unknown>) => http.patch(`/asset-contracts/${contractId}`, payload),

  resourceLimits: (params: Record<string, unknown>) => http.get("/resource-limits", { params }),
  patchResourceLimit: (limitStateId: number, payload: Record<string, unknown>) =>
    http.patch(`/resource-limits/${limitStateId}`, payload),

  resourceUsageEvents: (params: Record<string, unknown>) => http.get("/resource-usage-events", { params }),
  createResourceUsageEvent: (payload: Record<string, unknown>) => http.post("/resource-usage-events", payload),

  usagePurposes: (params: Record<string, unknown>) => http.get("/usage-purposes", { params }),
  createUsagePurpose: (payload: Record<string, unknown>) => http.post("/usage-purposes", payload),

  workOutputs: (params: Record<string, unknown>) => http.get("/work-outputs", { params }),
  createWorkOutput: (payload: Record<string, unknown>) => http.post("/work-outputs", payload),
  submitWorkOutput: (workOutputId: number) => http.post(`/work-outputs/${workOutputId}/submit`),
  approveWorkOutput: (workOutputId: number, payload: Record<string, unknown>) =>
    http.post(`/work-outputs/${workOutputId}/approve`, payload),
  rejectWorkOutput: (workOutputId: number, payload: Record<string, unknown>) =>
    http.post(`/work-outputs/${workOutputId}/reject`, payload),

  analyticsRoi: (params: Record<string, unknown>) => http.get("/analytics/roi", { params }),

  models: (params: Record<string, unknown>) => http.get("/models", { params }),
  usageEvents: (params: Record<string, unknown>) => http.get("/usage-events", { params }),

  costsSummary: (params: Record<string, unknown>) => http.get("/costs/summary", { params }),
  costsByUser: (params: Record<string, unknown>) => http.get("/costs/by-user", { params }),
  costsByDepartment: (params: Record<string, unknown>) => http.get("/costs/by-department", { params }),
  costsByModel: (params: Record<string, unknown>) => http.get("/costs/by-model", { params }),

  approvals: (params: Record<string, unknown>) => http.get("/approval-requests", { params }),
  approveRequest: (requestId: number, payload: Record<string, unknown>) =>
    http.post(`/approval-requests/${requestId}/approve`, payload),
  rejectRequest: (requestId: number, payload: Record<string, unknown>) =>
    http.post(`/approval-requests/${requestId}/reject`, payload),
  returnRequest: (requestId: number, payload: Record<string, unknown>) =>
    http.post(`/approval-requests/${requestId}/return`, payload),

  createExport: (payload: Record<string, unknown>) => http.post("/exports", payload),
  listExports: () => http.get("/exports"),

  lavaConnections: () => http.get("/lava/connection/list"),
  lavaCreateConnection: () => http.post("/lava/connection/create"),
  lavaDeleteConnection: (connectionId: number) => http.delete(`/lava/connection/${connectionId}`),
  lavaUpdateConnection: (payload: Record<string, unknown>) => http.post("/lava/connection/update", payload),
  lavaFetchModels: (payload: Record<string, unknown>) => http.post("/lava/connection/fetch-models", payload),
  lavaTestConnection: (payload: Record<string, unknown>) => http.post("/lava/connection/test", payload),

  lavaBindings: () => http.get("/lava/binding/list"),
  lavaUpdateBinding: (payload: Record<string, unknown>) => http.post("/lava/binding/update", payload),
  lavaLockBinding: (payload: Record<string, unknown>) => http.post("/lava/binding/lock", payload),
  lavaUnlockBinding: (payload: Record<string, unknown>) => http.post("/lava/binding/unlock", payload),
  lavaTestBinding: (payload: Record<string, unknown>) => http.post("/lava/binding/test", payload),

  lavaRuntimeCPU: () => http.get("/lava/runtime/cpu"),
  lavaUpdateRuntimeCPU: (payload: Record<string, unknown>) => http.post("/lava/runtime/cpu", payload),
  lavaRuntimeFlowaWorkers: () => http.get("/lava/runtime/flowa_workers"),
  lavaUpdateRuntimeFlowaWorkers: (payload: Record<string, unknown>) => http.post("/lava/runtime/flowa_workers", payload),

  assistantChat: (payload: Record<string, unknown>) => http.post("/assistant/chat", payload),
  assistantConversations: (params: Record<string, unknown>) => http.get("/assistant/conversations", { params }),
  assistantConversationMessages: (conversationId: number, params: Record<string, unknown>) =>
    http.get(`/assistant/conversations/${conversationId}/messages`, { params }),
};
