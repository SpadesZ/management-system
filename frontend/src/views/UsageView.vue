<!-- File Path: frontend/src/views/UsageView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <span>Usage Events</span>
        <div class="actions">
          <el-date-picker v-model="range" type="daterange" unlink-panels value-format="YYYY-MM-DD" />
          <el-button @click="load">查詢</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" height="560">
      <el-table-column prop="request_id" label="Request ID" min-width="200" />
      <el-table-column prop="created_at" label="Time" min-width="180" />
      <el-table-column prop="user_id" label="User" width="90" />
      <el-table-column prop="department_id" label="Dept" width="90" />
      <el-table-column prop="provider_id" label="Provider" width="90" />
      <el-table-column prop="model_id" label="Model" width="90" />
      <el-table-column prop="total_tokens" label="Tokens" width="120" />
      <el-table-column prop="estimated_cost_usd" label="Cost" width="120" />
      <el-table-column prop="status" label="Status" width="120" />
    </el-table>

    <div class="pager">
      <el-pagination
        layout="total, prev, pager, next"
        :current-page="page"
        :page-size="pageSize"
        :total="total"
        @current-change="onPageChange"
      />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

const rows = ref<any[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const range = ref<[string, string] | null>(null);

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const params: Record<string, unknown> = { page: page.value, page_size: pageSize.value, sort_by: "created_at" };
    if (range.value) {
      params.start_at = `${range.value[0]}T00:00:00Z`;
      params.end_at = `${range.value[1]}T23:59:59Z`;
    }
    const { data } = await api.usageEvents(params);
    rows.value = data.items;
    total.value = data.meta.total;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail?.message || "載入使用紀錄失敗");
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

.actions {
  display: flex;
  gap: 8px;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
