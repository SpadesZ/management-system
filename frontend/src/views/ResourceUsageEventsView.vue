<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <div>
          <div class="title">Token 資源使用事件</div>
          <div class="hint">資源池消耗明細與人工補單入口</div>
        </div>
        <div class="actions">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            unlink-panels
            value-format="YYYY-MM-DD"
          />
          <el-button @click="reloadByFilter">查詢</el-button>
          <el-button @click="load">重新整理</el-button>
          <el-button type="primary" @click="showCreateDialog = true">新增事件</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column prop="occurred_at" label="Occurred At" min-width="180" />
      <el-table-column prop="event_source" label="Source" width="120" />
      <el-table-column prop="request_id" label="Request ID" min-width="160" />
      <el-table-column prop="external_event_id" label="External Event" min-width="160" />
      <el-table-column label="資產" min-width="160">
        <template #default="scope">{{ assetLabel(scope.row) }}</template>
      </el-table-column>
      <el-table-column prop="department_id" label="Dept" width="90" />
      <el-table-column prop="project_id" label="Project" width="90" />
      <el-table-column prop="actor_user_id" label="Actor" width="90" />
      <el-table-column prop="total_tokens" label="Tokens" width="120" />
      <el-table-column prop="estimated_cost_usd" label="Cost USD" width="130" />
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

  <el-dialog v-model="showCreateDialog" title="新增 Resource Usage Event" width="760px">
    <el-form label-width="130px">
      <el-form-item label="資產類型">
        <el-radio-group v-model="createForm.assetType">
          <el-radio-button label="API_KEY" value="API_KEY" />
          <el-radio-button label="AI_ACCOUNT" value="AI_ACCOUNT" />
        </el-radio-group>
      </el-form-item>

      <el-form-item :label="createForm.assetType === 'API_KEY' ? 'API Key ID' : 'AI Account ID'">
        <el-input-number v-model="createForm.assetId" :min="1" controls-position="right" style="width: 260px" />
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
          <el-form-item label="Actor User ID">
            <el-input-number v-model="createForm.actorUserId" :min="1" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="Request ID">
            <el-input v-model="createForm.requestId" maxlength="80" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="External Event ID">
            <el-input v-model="createForm.externalEventId" maxlength="128" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="8">
          <el-form-item label="Input Tokens">
            <el-input-number v-model="createForm.inputTokens" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-form-item label="Output Tokens">
            <el-input-number v-model="createForm.outputTokens" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-form-item label="Total Tokens">
            <el-input-number v-model="createForm.totalTokens" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="8">
          <el-form-item label="Cost USD">
            <el-input v-model="createForm.estimatedCostUsd" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-form-item label="Currency">
            <el-input v-model="createForm.currency" maxlength="16" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-form-item label="Event Source">
            <el-input v-model="createForm.eventSource" maxlength="64" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="Occurred At">
        <el-date-picker
          v-model="createForm.occurredAt"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss[Z]"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="Metadata JSON">
        <el-input
          v-model="createForm.metadataText"
          type="textarea"
          :rows="4"
          placeholder='例如 {"source":"manual-adjustment"}'
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="showCreateDialog = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="createEvent">建立</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

interface ResourceUsageEventItem {
  id: number;
  api_key_id: number | null;
  ai_account_id: number | null;
  department_id: number | null;
  project_id: number | null;
  actor_user_id: number | null;
  request_id: string | null;
  event_source: string;
  external_event_id: string | null;
  total_tokens: number;
  estimated_cost_usd: string;
  occurred_at: string;
}

const rows = ref<ResourceUsageEventItem[]>([]);
const loading = ref(false);
const creating = ref(false);
const showCreateDialog = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const dateRange = ref<[string, string] | null>(null);

const createForm = reactive({
  assetType: "API_KEY",
  assetId: undefined as number | undefined,
  departmentId: undefined as number | undefined,
  projectId: undefined as number | undefined,
  actorUserId: undefined as number | undefined,
  requestId: "",
  externalEventId: "",
  inputTokens: 0,
  outputTokens: 0,
  totalTokens: undefined as number | undefined,
  estimatedCostUsd: "0.000000",
  currency: "USD",
  eventSource: "MANUAL",
  occurredAt: "",
  metadataText: "{}",
});

const assetLabel = (row: ResourceUsageEventItem): string => {
  if (row.api_key_id !== null) {
    return `API_KEY:${row.api_key_id}`;
  }
  if (row.ai_account_id !== null) {
    return `AI_ACCOUNT:${row.ai_account_id}`;
  }
  return "-";
};

const buildQuery = (): Record<string, unknown> => {
  const params: Record<string, unknown> = {
    page: page.value,
    page_size: pageSize.value,
    sort_by: "occurred_at",
    sort_order: "desc",
  };
  if (dateRange.value) {
    params.start_at = `${dateRange.value[0]}T00:00:00Z`;
    params.end_at = `${dateRange.value[1]}T23:59:59Z`;
  }
  return params;
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.resourceUsageEvents(buildQuery());
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入 resource usage events 失敗");
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
  createForm.assetType = "API_KEY";
  createForm.assetId = undefined;
  createForm.departmentId = undefined;
  createForm.projectId = undefined;
  createForm.actorUserId = undefined;
  createForm.requestId = "";
  createForm.externalEventId = "";
  createForm.inputTokens = 0;
  createForm.outputTokens = 0;
  createForm.totalTokens = undefined;
  createForm.estimatedCostUsd = "0.000000";
  createForm.currency = "USD";
  createForm.eventSource = "MANUAL";
  createForm.occurredAt = "";
  createForm.metadataText = "{}";
};

const parseMetadata = (rawText: string): Record<string, unknown> => {
  const text = rawText.trim();
  if (!text) {
    return {};
  }
  const parsed = JSON.parse(text);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("metadata_json 必須是 JSON 物件");
  }
  return parsed as Record<string, unknown>;
};

const createEvent = async (): Promise<void> => {
  if (!createForm.assetId) {
    ElMessage.warning("請輸入資產 ID");
    return;
  }

  creating.value = true;
  try {
    const payload: Record<string, unknown> = {
      department_id: createForm.departmentId,
      project_id: createForm.projectId,
      actor_user_id: createForm.actorUserId,
      request_id: createForm.requestId.trim() || null,
      event_source: createForm.eventSource.trim() || "MANUAL",
      external_event_id: createForm.externalEventId.trim() || null,
      input_tokens: createForm.inputTokens,
      output_tokens: createForm.outputTokens,
      estimated_cost_usd: createForm.estimatedCostUsd.trim() || "0.000000",
      currency: (createForm.currency.trim() || "USD").toUpperCase(),
      occurred_at: createForm.occurredAt || new Date().toISOString(),
      metadata_json: parseMetadata(createForm.metadataText),
    };

    if (createForm.totalTokens !== undefined && createForm.totalTokens !== null) {
      payload.total_tokens = createForm.totalTokens;
    }

    if (createForm.assetType === "API_KEY") {
      payload.api_key_id = createForm.assetId;
    } else {
      payload.ai_account_id = createForm.assetId;
    }

    await api.createResourceUsageEvent(payload);
    ElMessage.success("resource usage event 建立成功");
    showCreateDialog.value = false;
    resetCreateForm();
    page.value = 1;
    await load();
  } catch (error: any) {
    if (error instanceof Error && !error?.response) {
      ElMessage.error(error.message);
    } else {
      ElMessage.error(error?.response?.data?.detail || "建立 resource usage event 失敗");
    }
  } finally {
    creating.value = false;
  }
};

onMounted(load);
</script>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.title {
  font-size: 18px;
  font-weight: 700;
  color: #173a63;
}

.hint {
  margin-top: 4px;
  color: #607793;
  font-size: 12px;
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .header-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
