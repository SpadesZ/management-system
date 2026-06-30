<!-- File Path: frontend/src/views/MyOutputsView.vue -->
<!-- Timestamp: 2026-05-26T21:20:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <div>
          <div class="title">我的產出</div>
          <div class="hint">只顯示由我建立的 work outputs，可直接送審</div>
        </div>
        <el-button @click="load">重新整理</el-button>
      </div>
    </template>

    <div class="filters">
      <el-select v-model="statusFilter" clearable placeholder="狀態" style="width: 180px">
        <el-option label="DRAFT" value="DRAFT" />
        <el-option label="SUBMITTED" value="SUBMITTED" />
        <el-option label="APPROVED" value="APPROVED" />
        <el-option label="REJECTED" value="REJECTED" />
      </el-select>
      <el-button @click="reloadByFilter">查詢</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column prop="usage_purpose_id" label="Purpose" width="100" />
      <el-table-column prop="output_title" label="Title" min-width="220" show-overflow-tooltip />
      <el-table-column prop="total_tokens" label="Tokens" width="110" />
      <el-table-column prop="cost_usd" label="Cost USD" width="120" />
      <el-table-column prop="value_usd" label="Value USD" width="120" />
      <el-table-column prop="status" label="Status" width="120">
        <template #default="scope">
          <el-tag :type="tagType(scope.row.status)">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="Created At" min-width="180" />
      <el-table-column label="Action" width="140" fixed="right">
        <template #default="scope">
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="!canSubmit(scope.row.status)"
            @click="submitOutput(scope.row.id)"
          >
            送審
          </el-button>
        </template>
      </el-table-column>
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

interface OutputItem {
  id: number;
  usage_purpose_id: number;
  output_title: string;
  total_tokens: number;
  cost_usd: string;
  value_usd: string;
  status: string;
  created_at: string;
}

const rows = ref<OutputItem[]>([]);
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
  if (status === "SUBMITTED") {
    return "warning";
  }
  return "info";
};

const canSubmit = (status: string): boolean => {
  return status === "DRAFT" || status === "REJECTED";
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
      sort_by: "created_at",
      sort_order: "desc",
    };

    if (statusFilter.value) {
      params.status = statusFilter.value;
    }

    const { data } = await api.myOutputs(params);
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入我的產出失敗");
  } finally {
    loading.value = false;
  }
};

const submitOutput = async (workOutputId: number): Promise<void> => {
  try {
    await api.submitWorkOutput(workOutputId);
    ElMessage.success("已送審");
    await load();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "送審失敗");
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
