<!-- File Path: frontend/src/views/ExportsView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <span>報表匯出治理</span>
        <div>
          <el-button type="primary" @click="createExport">建立匯出任務</el-button>
          <el-button @click="load">重新整理</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" height="520">
      <el-table-column prop="id" label="Job ID" width="100" />
      <el-table-column prop="requester_user_id" label="Requester" width="120" />
      <el-table-column prop="export_type" label="Type" width="140" />
      <el-table-column prop="status" label="Status" width="120" />
      <el-table-column prop="file_path" label="File" min-width="260" />
      <el-table-column prop="expires_at" label="Expires" min-width="180" />
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

const rows = ref<any[]>([]);
const loading = ref(false);

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.listExports();
    rows.value = data;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail?.message || "載入匯出任務失敗");
  } finally {
    loading.value = false;
  }
};

const createExport = async (): Promise<void> => {
  try {
    await api.createExport({ export_type: "cost_ledger_csv", filters_json: {} });
    ElMessage.success("已建立匯出任務");
    await load();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail?.message || "建立匯出任務失敗");
  }
};

onMounted(load);
</script>

<style scoped>
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
