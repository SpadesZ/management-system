<!-- File Path: frontend/src/views/MyAssetsView.vue -->
<!-- Timestamp: 2026-05-26T21:20:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <div>
          <div class="title">我的資產</div>
          <div class="hint">顯示我擁有或已授權的 API Key 與 AI 帳號</div>
        </div>
        <el-button @click="load">重新整理</el-button>
      </div>
    </template>

    <div class="stats">
      <el-tag type="primary">API Keys: {{ apiKeysTotal }}</el-tag>
      <el-tag type="success">AI Accounts: {{ aiAccountsTotal }}</el-tag>
    </div>

    <el-tabs type="border-card">
      <el-tab-pane label="My API Keys">
        <el-table :data="apiKeys" v-loading="loading" height="280">
          <el-table-column prop="id" label="ID" width="90" />
          <el-table-column prop="name" label="Name" min-width="160" />
          <el-table-column prop="provider_id" label="Provider" width="110" />
          <el-table-column prop="masked_key" label="Masked Key" width="180" />
          <el-table-column prop="status" label="Status" width="120" />
          <el-table-column prop="expires_at" label="Expires At" min-width="180" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="My AI Accounts">
        <el-table :data="aiAccounts" v-loading="loading" height="280">
          <el-table-column prop="id" label="ID" width="90" />
          <el-table-column prop="vendor" label="Vendor" width="140" />
          <el-table-column prop="product" label="Product" width="160" />
          <el-table-column prop="plan" label="Plan" width="120" />
          <el-table-column prop="seats" label="Seats" width="100" />
          <el-table-column prop="monthly_cost_usd" label="Monthly Cost" width="140" />
          <el-table-column prop="owner_user_id" label="Owner" width="100" />
          <el-table-column prop="status" label="Status" width="120" />
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <div class="pager">
      <el-pagination
        layout="total, prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="Math.max(apiKeysTotal, aiAccountsTotal)"
        @current-change="onPageChange"
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

interface APIKeyItem {
  id: number;
  name: string;
  provider_id: number;
  masked_key: string;
  status: string;
  expires_at: string | null;
}

interface AIAccountItem {
  id: number;
  vendor: string;
  product: string;
  plan: string;
  seats: number;
  monthly_cost_usd: string;
  owner_user_id: number;
  status: string;
}

const apiKeys = ref<APIKeyItem[]>([]);
const aiAccounts = ref<AIAccountItem[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const apiKeysTotal = ref(0);
const aiAccountsTotal = ref(0);

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.myAssets({
      page: page.value,
      page_size: pageSize.value,
      sort_by: "created_at",
      sort_order: "desc",
    });
    apiKeys.value = Array.isArray(data?.api_keys) ? data.api_keys : [];
    aiAccounts.value = Array.isArray(data?.ai_accounts) ? data.ai_accounts : [];
    apiKeysTotal.value = Number(data?.meta?.api_keys_total || 0);
    aiAccountsTotal.value = Number(data?.meta?.ai_accounts_total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入我的資產失敗");
  } finally {
    loading.value = false;
  }
};

const onPageChange = async (nextPage: number): Promise<void> => {
  page.value = nextPage;
  await load();
};

onMounted(load);
</script>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-weight: 700;
  font-size: 18px;
}

.hint {
  color: #64748b;
  font-size: 13px;
  margin-top: 2px;
}

.stats {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
