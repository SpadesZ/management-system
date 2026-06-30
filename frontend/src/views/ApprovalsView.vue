<!-- File Path: frontend/src/views/ApprovalsView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="row">
        <span>申請審批中心</span>
        <div class="actions">
          <el-select v-model="statusFilter" clearable placeholder="狀態" style="width: 160px">
            <el-option label="PENDING" value="PENDING" />
            <el-option label="APPROVED" value="APPROVED" />
            <el-option label="REJECTED" value="REJECTED" />
            <el-option label="CANCELLED" value="CANCELLED" />
          </el-select>
          <el-button @click="reloadByFilter">查詢</el-button>
          <el-button @click="load">重新整理</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="100" />
      <el-table-column prop="requester_id" label="Requester" width="120" />
      <el-table-column prop="request_type" label="Request Type" width="150" />
      <el-table-column prop="target_type" label="Target Type" width="140" />
      <el-table-column prop="target_id" label="Target" width="110" />
      <el-table-column prop="status" label="Status" width="130">
        <template #default="scope">
          <el-tag :type="statusTagType(scope.row.status)">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="reason" label="Reason" min-width="220" />
      <el-table-column label="Actions" min-width="320" fixed="right">
        <template #default="scope">
          <el-button
            size="small"
            type="success"
            plain
            :disabled="!canDecide(scope.row)"
            @click="decide(scope.row.id, 'approve')"
          >
            核准
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="!canDecide(scope.row)"
            @click="decide(scope.row.id, 'reject')"
          >
            拒絕
          </el-button>
          <el-button
            size="small"
            type="warning"
            plain
            :disabled="!canDecide(scope.row)"
            @click="decide(scope.row.id, 'return')"
          >
            退回
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
import { ElMessage, ElMessageBox } from "element-plus";

import { api } from "../api/endpoints";

type ApprovalAction = "approve" | "reject" | "return";

interface ApprovalItem {
  id: number;
  requester_id: number;
  request_type: string;
  target_type: string;
  target_id: number | null;
  reason: string;
  status: string;
}

const rows = ref<ApprovalItem[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const statusFilter = ref<string | undefined>(undefined);

const statusTagType = (status: string): "primary" | "success" | "warning" | "danger" | "info" => {
  if (status === "APPROVED") {
    return "success";
  }
  if (status === "REJECTED") {
    return "danger";
  }
  if (status === "CANCELLED") {
    return "warning";
  }
  return "info";
};

const canDecide = (row: ApprovalItem): boolean => {
  return row.status === "PENDING";
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const params: Record<string, unknown> = { page: page.value, page_size: pageSize.value };
    if (statusFilter.value) {
      params.status = statusFilter.value;
    }
    const { data } = await api.approvals(params);
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail?.message || "載入審核資料失敗");
  } finally {
    loading.value = false;
  }
};

const reloadByFilter = async (): Promise<void> => {
  page.value = 1;
  await load();
};

const decide = async (requestId: number, action: ApprovalAction): Promise<void> => {
  const actionName = action === "approve" ? "核准" : action === "reject" ? "拒絕" : "退回";
  try {
    const promptResult = await ElMessageBox.prompt(`請輸入${actionName}理由`, `${actionName}申請`, {
      confirmButtonText: actionName,
      cancelButtonText: "取消",
      inputPlaceholder: `${actionName}理由`,
      inputValidator: (value: string) => {
        if (!value || !value.trim()) {
          return "理由必填";
        }
        return true;
      },
    });

    const payload = { decision_reason: promptResult.value.trim() };
    if (action === "approve") {
      await api.approveRequest(requestId, payload);
    } else if (action === "reject") {
      await api.rejectRequest(requestId, payload);
    } else {
      await api.returnRequest(requestId, payload);
    }

    ElMessage.success(`${actionName}成功`);
    await load();
  } catch (error: any) {
    if (error === "cancel" || error === "close") {
      return;
    }
    ElMessage.error(error?.response?.data?.detail || `${actionName}失敗`);
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
