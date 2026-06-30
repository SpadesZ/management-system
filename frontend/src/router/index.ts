// File Path: frontend/src/router/index.ts
// Timestamp: 2026-05-26T21:20:00+08:00
// Version: v0.3

import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../layout/AppLayout.vue";
import LoginView from "../views/LoginView.vue";
import RegisterView from "../views/RegisterView.vue";
import DashboardView from "../views/DashboardView.vue";
import UsersView from "../views/UsersView.vue";
import DepartmentsView from "../views/DepartmentsView.vue";
import ProjectsView from "../views/ProjectsView.vue";
import APIKeysView from "../views/APIKeysView.vue";
import AIAccountsView from "../views/AIAccountsView.vue";
import ModelsView from "../views/ModelsView.vue";
import UsageView from "../views/UsageView.vue";
import CostsView from "../views/CostsView.vue";
import ApprovalsView from "../views/ApprovalsView.vue";
import ExportsView from "../views/ExportsView.vue";
import AssetContractsView from "../views/AssetContractsView.vue";
import ResourceLimitsView from "../views/ResourceLimitsView.vue";
import ResourceUsageEventsView from "../views/ResourceUsageEventsView.vue";
import LavaSetupView from "../views/LavaSetupView.vue";
import AssistantView from "../views/AssistantView.vue";
import UsagePurposesView from "../views/UsagePurposesView.vue";
import WorkOutputsView from "../views/WorkOutputsView.vue";
import ROIAnalyticsView from "../views/ROIAnalyticsView.vue";
import AssistantHistoryView from "../views/AssistantHistoryView.vue";
import MyAssetsView from "../views/MyAssetsView.vue";
import MyRequestsView from "../views/MyRequestsView.vue";
import MyOutputsView from "../views/MyOutputsView.vue";

const routes = [
  {
    path: "/login",
    name: "login",
    component: LoginView,
  },
  {
    path: "/register",
    name: "register",
    component: RegisterView,
  },
  {
    path: "/",
    component: AppLayout,
    children: [
      { path: "", redirect: "/dashboard" },
      { path: "/dashboard", name: "dashboard", component: DashboardView },
      { path: "/users", name: "users", component: UsersView },
      { path: "/departments", name: "departments", component: DepartmentsView },
      { path: "/projects", name: "projects", component: ProjectsView },
      { path: "/api-keys", name: "api-keys", component: APIKeysView },
      { path: "/ai-accounts", name: "ai-accounts", component: AIAccountsView },
      { path: "/models", name: "models", component: ModelsView },
      { path: "/usage-events", name: "usage-events", component: UsageView },
      { path: "/usage-purposes", name: "usage-purposes", component: UsagePurposesView },
      { path: "/work-outputs", name: "work-outputs", component: WorkOutputsView },
      { path: "/my-assets", name: "my-assets", component: MyAssetsView },
      { path: "/my-requests", name: "my-requests", component: MyRequestsView },
      { path: "/my-outputs", name: "my-outputs", component: MyOutputsView },
      { path: "/costs", name: "costs", component: CostsView },
      { path: "/asset-contracts", name: "asset-contracts", component: AssetContractsView },
      { path: "/resource-limits", name: "resource-limits", component: ResourceLimitsView },
      { path: "/resource-usage-events", name: "resource-usage-events", component: ResourceUsageEventsView },
      { path: "/analytics-roi", name: "analytics-roi", component: ROIAnalyticsView },
      { path: "/approvals", name: "approvals", component: ApprovalsView },
      { path: "/exports", name: "exports", component: ExportsView },
      { path: "/lava-setup", name: "lava-setup", component: LavaSetupView },
      { path: "/assistant", name: "assistant", component: AssistantView },
      { path: "/assistant-history", name: "assistant-history", component: AssistantHistoryView },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem("access_token");
  const publicPaths = new Set(["/login", "/register"]);
  if (!publicPaths.has(to.path) && !token) {
    next("/login");
    return;
  }
  if (publicPaths.has(to.path) && token) {
    next("/dashboard");
    return;
  }
  next();
});

export default router;
