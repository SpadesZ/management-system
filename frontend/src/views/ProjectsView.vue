<!-- File Path: frontend/src/views/ProjectsView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <span>專案管理</span>
        <el-button @click="load">重新整理</el-button>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="id" label="ID" width="100" />
      <el-table-column prop="code" label="Code" width="130" />
      <el-table-column prop="name" label="專案名稱" min-width="180" />
      <el-table-column prop="department_id" label="部門" width="120" />
      <el-table-column prop="owner_user_id" label="Owner" width="120" />
      <el-table-column prop="status" label="狀態" width="120" />
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

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.projects({ page: page.value, page_size: pageSize.value });
    rows.value = data.items;
    total.value = data.meta.total;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail?.message || "載入專案失敗");
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

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
