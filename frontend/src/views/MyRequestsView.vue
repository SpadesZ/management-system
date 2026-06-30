<!-- File Path: frontend/src/views/MyRequestsView.vue -->
<!-- Timestamp: 2026-05-26T21:20:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <div>
          <div class="title">我的申請</div>
          <div class="hint">只顯示由我提出的 approval requests</div>
        </div>
        <el-button @click="load">重新整理</el-button>
      </div>
    </template>

    <div class="filters">
      <el-select v-model="statusFilter" clearable placeholder="狀態" style="width: 180px">
        <el-option label="PENDING" value="PENDING" />
        <el-option label="APPROVED" value="APPROVED" />
        <el-option label="REJECTED" value="REJECTED" />
        <el-option label="CANCELLED" value="CANCELLED" />
      </el-select>
      <el-button @click="reloadByFilter">查詢</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column prop="request_type" label="Request Type" width="160" />
      <el-table-column prop="target_type" label="Target Type" width="150" />
      <el-table-column prop="target_id" label="Target ID" width="120" />
      <el-table-column prop="status" label="Status" width="120">
        <template #default="scope">
          <el-tag :type="tagType(scope.row.status)">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="Reason" min-width="320" show-overflow-tooltip />
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

interface RequestItem {
  id: number;
  request_type: string;
  target_type: string;
  target_id: number | null;
  status: string;
  reason: string;
}

const rows = ref<RequestItem[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const statusFilter = ref("");

const tagType = (status: string): "primary" | "success" | "warning" | "danger" | "info" => {
  if (status === "APPROVED") {
    return "success";
  }
  if (status === "REJECTED") {
    return "danger";
  }
  if (status === "PENDING") {
    return "warning";
  }
  return "info";
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
      sort_by: "id",
      sort_order: "desc",
    };
    if (statusFilter.value) {
      params.status = statusFilter.value;
    }

    const { data } = await api.myRequests(params);
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入我的申請失敗");
  } finally {
    loading.value = false;
  }
};

const reloadByFilter = async (): Promise<void> => {
  page.value = 1;
  await load();
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

.filters {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
