<!-- File Path: frontend/src/views/CostsView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <div class="grid">
    <el-card>
      <template #header>成本總覽</template>
      <div class="stat">Requests: {{ summary.request_count }}</div>
      <div class="stat">Tokens: {{ summary.total_tokens }}</div>
      <div class="stat">Cost USD: {{ Number(summary.total_cost_usd || 0).toFixed(6) }}</div>
    </el-card>

    <el-card>
      <template #header>By Department</template>
      <el-table :data="byDepartment" height="320">
        <el-table-column prop="department_id" label="Department" width="120" />
        <el-table-column prop="request_count" label="Requests" width="120" />
        <el-table-column prop="total_tokens" label="Tokens" width="160" />
        <el-table-column prop="total_cost_usd" label="Cost USD" min-width="140" />
      </el-table>
    </el-card>

    <el-card>
      <template #header>By User</template>
      <el-table :data="byUser" height="320">
        <el-table-column prop="user_id" label="User" width="120" />
        <el-table-column prop="request_count" label="Requests" width="120" />
        <el-table-column prop="total_tokens" label="Tokens" width="160" />
        <el-table-column prop="total_cost_usd" label="Cost USD" min-width="140" />
      </el-table>
    </el-card>

    <el-card>
      <template #header>By Model</template>
      <el-table :data="byModel" height="320">
        <el-table-column prop="model_id" label="Model" width="120" />
        <el-table-column prop="request_count" label="Requests" width="120" />
        <el-table-column prop="total_tokens" label="Tokens" width="160" />
        <el-table-column prop="total_cost_usd" label="Cost USD" min-width="140" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

const summary = ref<any>({ request_count: 0, total_tokens: 0, total_cost_usd: 0 });
const byDepartment = ref<any[]>([]);
const byUser = ref<any[]>([]);
const byModel = ref<any[]>([]);

const load = async (): Promise<void> => {
  try {
    const [summaryResp, deptResp, userResp, modelResp] = await Promise.all([
      api.costsSummary({}),
      api.costsByDepartment({}),
      api.costsByUser({}),
      api.costsByModel({}),
    ]);
    summary.value = summaryResp.data;
    byDepartment.value = deptResp.data.items;
    byUser.value = userResp.data.items;
    byModel.value = modelResp.data.items;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail?.message || "載入成本資料失敗");
  }
};

onMounted(load);
</script>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.stat {
  font-size: 16px;
  margin-bottom: 8px;
  color: #1c3554;
}

@media (max-width: 1100px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
