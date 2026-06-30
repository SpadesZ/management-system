<!-- File Path: frontend/src/layout/AppLayout.vue -->
<!-- Timestamp: 2026-05-26T21:20:00+08:00 -->
<!-- Version: v0.3 -->

<template>
  <el-container class="shell">
    <el-aside width="280px" class="sidebar">
      <div class="brand-main">TokenButler</div>
      <div class="brand-sub">八大治理模組</div>

      <el-menu :default-active="$route.path" :default-openeds="defaultOpeneds" router class="menu" background-color="transparent">
        <el-sub-menu index="module-1">
          <template #title>1. 組織人員</template>
          <el-menu-item index="/users">使用者管理</el-menu-item>
          <el-menu-item index="/departments">部門管理</el-menu-item>
          <el-menu-item index="/projects">專案管理</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-2">
          <template #title>2. Token 資產盤點</template>
          <el-menu-item index="/api-keys">API Key 資產</el-menu-item>
          <el-menu-item index="/ai-accounts">AI 帳號資產</el-menu-item>
          <el-menu-item index="/models">模型資產</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-3">
          <template #title>3. Token 支出財務</template>
          <el-menu-item index="/costs">成本總覽</el-menu-item>
          <el-menu-item index="/asset-contracts">合約與訂閱治理</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-4">
          <template #title>4. Token 資源使用</template>
          <el-menu-item index="/usage-events">Usage Events</el-menu-item>
          <el-menu-item index="/resource-limits">Limit State</el-menu-item>
          <el-menu-item index="/resource-usage-events">Resource Events</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-5">
          <template #title>5. Token 使用人員/應用</template>
          <el-menu-item index="/usage-purposes">使用用途</el-menu-item>
          <el-menu-item index="/work-outputs">產出與價值</el-menu-item>
          <el-menu-item index="/my-assets">我的資產</el-menu-item>
          <el-menu-item index="/my-outputs">我的產出</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-6">
          <template #title>6. Token 人員申請</template>
          <el-menu-item index="/my-requests">我的申請</el-menu-item>
          <el-menu-item index="/approvals">審批中心</el-menu-item>
          <el-menu-item index="/exports">報表匯出</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-7">
          <template #title>7. Token 使用分析</template>
          <el-menu-item index="/dashboard">儀表板</el-menu-item>
          <el-menu-item index="/analytics-roi">ROI 分析</el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="module-8">
          <template #title>8. Office 客服 / Ask FinOps</template>
          <el-menu-item index="/assistant">Ask FinOps</el-menu-item>
          <el-menu-item index="/assistant-history">歷史對話</el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="showSystemSettings" index="system">
          <template #title>系統設定</template>
          <el-menu-item index="/lava-setup">LAVA Setup</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="title">TokenButler 八大治理平台</div>
        <div class="actions">
          <el-button type="danger" plain @click="logout">登出</el-button>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { api } from "../api/endpoints";

const router = useRouter();
const myRole = ref("");

const defaultOpeneds = [
  "module-1",
  "module-2",
  "module-3",
  "module-4",
  "module-5",
  "module-6",
  "module-7",
  "module-8",
];

const showSystemSettings = computed(() => {
  return new Set(["ADMIN", "SECURITY"]).has(myRole.value);
});

const loadMyRole = async (): Promise<void> => {
  try {
    const { data } = await api.me();
    myRole.value = String(data?.role || "").toUpperCase();
  } catch {
    myRole.value = "";
  }
};

const logout = (): void => {
  localStorage.removeItem("access_token");
  router.push("/login");
};

onMounted(loadMyRole);
</script>

<style scoped>
.shell {
  min-height: 100vh;
  background: linear-gradient(165deg, #f8fbff 0%, #eaf1fb 65%, #dce8f8 100%);
}

.sidebar {
  border-right: 1px solid #d8e4f7;
  background: linear-gradient(180deg, #f4f9ff 0%, #eef5ff 100%);
  padding: 16px 12px;
}

.brand-main {
  font-size: 22px;
  font-weight: 700;
  color: #173a63;
  margin-bottom: 2px;
}

.brand-sub {
  font-size: 12px;
  letter-spacing: 1px;
  color: #5f7898;
  margin-bottom: 12px;
}

.menu {
  border-right: none;
}

.header {
  height: 64px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #d8e4f7;
  background: rgba(255, 255, 255, 0.65);
  backdrop-filter: blur(8px);
}

.title {
  font-size: 20px;
  font-weight: 700;
  color: #1f2d3d;
}

.main {
  padding: 20px;
}

@media (max-width: 900px) {
  .sidebar {
    width: 86px !important;
  }

  .brand-main {
    font-size: 12px;
  }

  .brand-sub {
    display: none;
  }

  .title {
    font-size: 16px;
  }
}
</style>
