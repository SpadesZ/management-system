<!-- File Path: frontend/src/views/UsersView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <span>使用者管理</span>
        <el-button @click="load">重新整理</el-button>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading">
      <el-table-column prop="id" label="ID" width="100" />
      <el-table-column prop="employee_no" label="員工編號" width="140" />
      <el-table-column prop="name" label="姓名" min-width="140" />
      <el-table-column prop="email" label="Email" min-width="180" />
      <el-table-column prop="department_id" label="部門" width="120" />
      <el-table-column prop="role" label="角色" width="120" />
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
    const { data } = await api.users({ page: page.value, page_size: pageSize.value });
    rows.value = data.items;
    total.value = data.meta.total;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail?.message || "載入使用者失敗");
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
