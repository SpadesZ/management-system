<!-- File Path: frontend/src/views/WorkOutputsView.vue -->
<!-- Timestamp: 2026-05-26T13:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <div>
          <div class="title">Work Outputs</div>
          <div class="hint">管理產出送審流程（DRAFT -> SUBMITTED -> APPROVED/REJECTED）</div>
        </div>
        <div class="actions">
          <el-button @click="load">重新整理</el-button>
          <el-button type="primary" @click="showCreateDialog = true">新增產出</el-button>
        </div>
      </div>
    </template>

    <div class="filters">
      <el-select v-model="filters.status" clearable placeholder="狀態" style="width: 160px">
        <el-option label="DRAFT" value="DRAFT" />
        <el-option label="SUBMITTED" value="SUBMITTED" />
        <el-option label="APPROVED" value="APPROVED" />
        <el-option label="REJECTED" value="REJECTED" />
      </el-select>
      <el-select v-model="filters.usagePurposeId" clearable filterable placeholder="Usage Purpose" style="width: 280px">
        <el-option v-for="item in usagePurposes" :key="item.id" :label="`${item.code} - ${item.name}`" :value="item.id" />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" unlink-panels />
      <el-button @click="reloadByFilter">查詢</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column prop="usage_purpose_id" label="Purpose" width="100" />
      <el-table-column prop="output_title" label="Title" min-width="220" show-overflow-tooltip />
      <el-table-column prop="department_id" label="Dept" width="90" />
      <el-table-column prop="user_id" label="Owner" width="90" />
      <el-table-column prop="total_tokens" label="Tokens" width="110" />
      <el-table-column prop="cost_usd" label="Cost USD" width="120" />
      <el-table-column prop="value_usd" label="Value USD" width="120" />
      <el-table-column prop="status" label="Status" width="120">
        <template #default="scope">
          <el-tag :type="tagType(scope.row.status)">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="Created At" min-width="180" />
      <el-table-column label="Actions" min-width="280" fixed="right">
        <template #default="scope">
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="!canSubmit(scope.row)"
            @click="submitOutput(scope.row.id)"
          >
            Submit
          </el-button>
          <el-button
            size="small"
            type="success"
            plain
            :disabled="!canReview(scope.row)"
            @click="approveOutput(scope.row.id)"
          >
            Approve
          </el-button>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="!canReview(scope.row)"
            @click="rejectOutput(scope.row.id)"
          >
            Reject
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

  <el-dialog v-model="showCreateDialog" title="新增 Work Output" width="760px">
    <el-form label-width="130px">
      <el-form-item label="Usage Purpose">
        <el-select v-model="createForm.usagePurposeId" filterable style="width: 100%" placeholder="選擇用途">
          <el-option v-for="item in usagePurposes" :key="item.id" :label="`${item.code} - ${item.name}`" :value="item.id" />
        </el-select>
      </el-form-item>

      <el-form-item label="Asset Type">
        <el-radio-group v-model="createForm.assetType">
          <el-radio-button label="API_KEY" value="API_KEY" />
          <el-radio-button label="AI_ACCOUNT" value="AI_ACCOUNT" />
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="createForm.assetType === 'API_KEY' ? 'API Key ID' : 'AI Account ID'">
        <el-input-number v-model="createForm.assetId" :min="1" controls-position="right" style="width: 240px" />
      </el-form-item>

      <el-row :gutter="12">
        <el-col :xs="24" :md="8">
          <el-form-item label="Department ID">
            <el-input-number v-model="createForm.departmentId" :min="1" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-form-item label="Project ID">
            <el-input-number v-model="createForm.projectId" :min="1" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-form-item label="Request ID">
            <el-input v-model="createForm.requestId" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="Output Title">
        <el-input v-model="createForm.outputTitle" maxlength="255" show-word-limit />
      </el-form-item>

      <el-form-item label="Output Summary">
        <el-input v-model="createForm.outputSummary" type="textarea" :rows="4" maxlength="8000" show-word-limit />
      </el-form-item>

      <el-row :gutter="12">
        <el-col :xs="24" :md="6">
          <el-form-item label="Input Tokens">
            <el-input-number v-model="createForm.inputTokens" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="6">
          <el-form-item label="Output Tokens">
            <el-input-number v-model="createForm.outputTokens" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="6">
          <el-form-item label="Cost USD">
            <el-input v-model="createForm.costUsd" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="6">
          <el-form-item label="Value USD">
            <el-input v-model="createForm.valueUsd" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <template #footer>
      <el-button @click="showCreateDialog = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="createOutput">建立</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { api } from "../api/endpoints";

interface UsagePurposeItem {
  id: number;
  code: string;
  name: string;
}

interface WorkOutputItem {
  id: number;
  usage_purpose_id: number;
  user_id: number;
  department_id: number;
  project_id: number | null;
  api_key_id: number | null;
  ai_account_id: number | null;
  output_title: string;
  output_summary: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: string;
  value_usd: string;
  status: string;
  created_at: string;
}

const rows = ref<WorkOutputItem[]>([]);
const usagePurposes = ref<UsagePurposeItem[]>([]);
const loading = ref(false);
const submitting = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const showCreateDialog = ref(false);
const myRole = ref("");
const myUserId = ref<number | null>(null);
const dateRange = ref<[string, string] | null>(null);

const filters = reactive({
  status: "",
  usagePurposeId: undefined as number | undefined,
});

const createForm = reactive({
  usagePurposeId: undefined as number | undefined,
  assetType: "API_KEY",
  assetId: undefined as number | undefined,
  departmentId: undefined as number | undefined,
  projectId: undefined as number | undefined,
  requestId: "",
  outputTitle: "",
  outputSummary: "",
  inputTokens: 0,
  outputTokens: 0,
  costUsd: "0.000000",
  valueUsd: "0.000000",
});

const canReviewByRole = computed(() => {
  return new Set(["ADMIN", "FINANCE", "MANAGER"]).has(myRole.value);
});

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

const loadMe = async (): Promise<void> => {
  try {
    const { data } = await api.me();
    myRole.value = String(data?.role || "").toUpperCase();
    myUserId.value = Number(data?.id || 0) || null;
  } catch {
    myRole.value = "";
    myUserId.value = null;
  }
};

const loadUsagePurposes = async (): Promise<void> => {
  try {
    const { data } = await api.usagePurposes({ page: 1, page_size: 200, sort_by: "code", sort_order: "asc" });
    usagePurposes.value = Array.isArray(data?.items) ? data.items : [];
  } catch {
    usagePurposes.value = [];
  }
};

const buildQuery = (): Record<string, unknown> => {
  const params: Record<string, unknown> = {
    page: page.value,
    page_size: pageSize.value,
    sort_by: "created_at",
    sort_order: "desc",
  };

  if (filters.status) {
    params.status = filters.status;
  }
  if (filters.usagePurposeId) {
    params.usage_purpose_id = filters.usagePurposeId;
  }
  if (dateRange.value) {
    params.start_at = `${dateRange.value[0]}T00:00:00Z`;
    params.end_at = `${dateRange.value[1]}T23:59:59Z`;
  }

  return params;
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.workOutputs(buildQuery());
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入 work outputs 失敗");
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

const resetCreateForm = (): void => {
  createForm.usagePurposeId = undefined;
  createForm.assetType = "API_KEY";
  createForm.assetId = undefined;
  createForm.departmentId = undefined;
  createForm.projectId = undefined;
  createForm.requestId = "";
  createForm.outputTitle = "";
  createForm.outputSummary = "";
  createForm.inputTokens = 0;
  createForm.outputTokens = 0;
  createForm.costUsd = "0.000000";
  createForm.valueUsd = "0.000000";
};

const createOutput = async (): Promise<void> => {
  if (!createForm.usagePurposeId) {
    ElMessage.warning("請選擇 Usage Purpose");
    return;
  }
  if (!createForm.assetId) {
    ElMessage.warning("請輸入資產 ID");
    return;
  }
  if (!createForm.outputTitle.trim()) {
    ElMessage.warning("請輸入 Output Title");
    return;
  }

  submitting.value = true;
  try {
    const payload: Record<string, unknown> = {
      usage_purpose_id: createForm.usagePurposeId,
      output_title: createForm.outputTitle.trim(),
      output_summary: createForm.outputSummary.trim() || null,
      input_tokens: createForm.inputTokens,
      output_tokens: createForm.outputTokens,
      cost_usd: createForm.costUsd,
      value_usd: createForm.valueUsd,
      request_id: createForm.requestId.trim() || null,
      department_id: createForm.departmentId,
      project_id: createForm.projectId,
      metadata_json: { source: "frontend-work-output" },
    };

    if (createForm.assetType === "API_KEY") {
      payload.api_key_id = createForm.assetId;
    } else {
      payload.ai_account_id = createForm.assetId;
    }

    await api.createWorkOutput(payload);
    ElMessage.success("Work output 建立成功");
    showCreateDialog.value = false;
    resetCreateForm();
    page.value = 1;
    await load();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "建立 work output 失敗");
  } finally {
    submitting.value = false;
  }
};

const canSubmit = (row: WorkOutputItem): boolean => {
  if (!(row.status === "DRAFT" || row.status === "REJECTED")) {
    return false;
  }
  if (canReviewByRole.value) {
    return true;
  }
  if (myUserId.value === null) {
    return false;
  }
  return Number(row.user_id) === myUserId.value;
};

const canReview = (row: WorkOutputItem): boolean => {
  return canReviewByRole.value && row.status === "SUBMITTED";
};

const submitOutput = async (id: number): Promise<void> => {
  try {
    await api.submitWorkOutput(id);
    ElMessage.success("送審成功");
    await load();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "送審失敗");
  }
};

const approveOutput = async (id: number): Promise<void> => {
  try {
    const result = await ElMessageBox.prompt("可輸入核准說明（選填）", "Approve Work Output", {
      confirmButtonText: "核准",
      cancelButtonText: "取消",
      inputValue: "",
    });
    await api.approveWorkOutput(id, { review_comment: result.value || null });
    ElMessage.success("核准成功");
    await load();
  } catch (error: any) {
    if (String(error) === "cancel") {
      return;
    }
    ElMessage.error(error?.response?.data?.detail || "核准失敗");
  }
};

const rejectOutput = async (id: number): Promise<void> => {
  try {
    const result = await ElMessageBox.prompt("請輸入拒絕原因（選填）", "Reject Work Output", {
      confirmButtonText: "拒絕",
      cancelButtonText: "取消",
      inputValue: "",
    });
    await api.rejectWorkOutput(id, { review_comment: result.value || null });
    ElMessage.success("已拒絕");
    await load();
  } catch (error: any) {
    if (String(error) === "cancel") {
      return;
    }
    ElMessage.error(error?.response?.data?.detail || "拒絕失敗");
  }
};

onMounted(async () => {
  await loadMe();
  await loadUsagePurposes();
  await load();
});
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.title {
  font-size: 18px;
  font-weight: 700;
  color: #173a63;
}

.hint {
  margin-top: 4px;
  font-size: 12px;
  color: #607793;
}

.actions {
  display: flex;
  gap: 8px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1000px) {
  .header-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
