<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <div>
          <div class="title">Token 資源使用</div>
          <div class="hint">5h / 日 / 週 / 月資源限制狀態</div>
        </div>
        <el-button @click="load">重新整理</el-button>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column label="資產" min-width="160">
        <template #default="scope">{{ assetLabel(scope.row) }}</template>
      </el-table-column>
      <el-table-column prop="tokens_5h" label="5h Tokens" width="110" />
      <el-table-column prop="tokens_today" label="Today" width="110" />
      <el-table-column prop="tokens_week" label="Week" width="110" />
      <el-table-column prop="tokens_month" label="Month" width="110" />
      <el-table-column label="5h Limit" width="110">
        <template #default="scope">{{ scope.row.limit_5h ?? "-" }}</template>
      </el-table-column>
      <el-table-column label="Day Limit" width="110">
        <template #default="scope">{{ scope.row.limit_day ?? "-" }}</template>
      </el-table-column>
      <el-table-column label="Week Limit" width="110">
        <template #default="scope">{{ scope.row.limit_week ?? "-" }}</template>
      </el-table-column>
      <el-table-column label="Month Limit" width="120">
        <template #default="scope">{{ scope.row.limit_month ?? "-" }}</template>
      </el-table-column>
      <el-table-column label="使用率" width="120">
        <template #default="scope">{{ formatPct(scope.row.utilization_pct) }}%</template>
      </el-table-column>
      <el-table-column prop="status" label="狀態" width="120">
        <template #default="scope">
          <el-tag :type="scope.row.status === 'ACTIVE' ? 'success' : 'warning'">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新時間" min-width="180" />
      <el-table-column label="Actions" width="110" fixed="right">
        <template #default="scope">
          <el-button size="small" plain @click="openEdit(scope.row)">調整</el-button>
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

  <el-dialog v-model="showEditDialog" title="調整資源限制" width="720px">
    <el-form label-width="130px">
      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="5h Tokens">
            <el-input-number v-model="editForm.tokens5h" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="Today Tokens">
            <el-input-number v-model="editForm.tokensToday" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="Week Tokens">
            <el-input-number v-model="editForm.tokensWeek" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="Month Tokens">
            <el-input-number v-model="editForm.tokensMonth" :min="0" controls-position="right" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="5h Limit">
            <el-input v-model="editForm.limit5h" placeholder="留空代表不限" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="Day Limit">
            <el-input v-model="editForm.limitDay" placeholder="留空代表不限" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="Week Limit">
            <el-input v-model="editForm.limitWeek" placeholder="留空代表不限" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="Month Limit">
            <el-input v-model="editForm.limitMonth" placeholder="留空代表不限" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="狀態">
        <el-select v-model="editForm.status" style="width: 100%">
          <el-option label="ACTIVE" value="ACTIVE" />
          <el-option label="INACTIVE" value="INACTIVE" />
          <el-option label="DISABLED" value="DISABLED" />
        </el-select>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="showEditDialog = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="saveEdit">儲存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

interface ResourceLimitItem {
  id: number;
  api_key_id: number | null;
  ai_account_id: number | null;
  tokens_5h: number;
  tokens_today: number;
  tokens_week: number;
  tokens_month: number;
  limit_5h: number | null;
  limit_day: number | null;
  limit_week: number | null;
  limit_month: number | null;
  utilization_pct: string;
  status: string;
  updated_at: string;
}

const rows = ref<ResourceLimitItem[]>([]);
const loading = ref(false);
const saving = ref(false);
const showEditDialog = ref(false);
const editingId = ref<number | null>(null);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const editForm = reactive({
  tokens5h: 0,
  tokensToday: 0,
  tokensWeek: 0,
  tokensMonth: 0,
  limit5h: "",
  limitDay: "",
  limitWeek: "",
  limitMonth: "",
  status: "ACTIVE",
});

const assetLabel = (row: ResourceLimitItem): string => {
  if (row.api_key_id !== null) {
    return `API_KEY:${row.api_key_id}`;
  }
  if (row.ai_account_id !== null) {
    return `AI_ACCOUNT:${row.ai_account_id}`;
  }
  return "-";
};

const formatPct = (value: string): string => {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return "0.00";
  }
  return numeric.toFixed(2);
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.resourceLimits({
      page: page.value,
      page_size: pageSize.value,
      sort_by: "updated_at",
      sort_order: "desc",
    });
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入資源限制狀態失敗");
  } finally {
    loading.value = false;
  }
};

const onPageChange = async (nextPage: number): Promise<void> => {
  page.value = nextPage;
  await load();
};

const openEdit = (row: ResourceLimitItem): void => {
  editingId.value = row.id;
  editForm.tokens5h = row.tokens_5h;
  editForm.tokensToday = row.tokens_today;
  editForm.tokensWeek = row.tokens_week;
  editForm.tokensMonth = row.tokens_month;
  editForm.limit5h = row.limit_5h === null ? "" : String(row.limit_5h);
  editForm.limitDay = row.limit_day === null ? "" : String(row.limit_day);
  editForm.limitWeek = row.limit_week === null ? "" : String(row.limit_week);
  editForm.limitMonth = row.limit_month === null ? "" : String(row.limit_month);
  editForm.status = row.status;
  showEditDialog.value = true;
};

const parseOptionalInt = (value: string): number | null => {
  if (!value.trim()) {
    return null;
  }
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric < 0) {
    throw new Error("限制值需為大於等於 0 的整數");
  }
  return numeric;
};

const saveEdit = async (): Promise<void> => {
  if (editingId.value === null) {
    return;
  }

  saving.value = true;
  try {
    const payload = {
      tokens_5h: editForm.tokens5h,
      tokens_today: editForm.tokensToday,
      tokens_week: editForm.tokensWeek,
      tokens_month: editForm.tokensMonth,
      limit_5h: parseOptionalInt(editForm.limit5h),
      limit_day: parseOptionalInt(editForm.limitDay),
      limit_week: parseOptionalInt(editForm.limitWeek),
      limit_month: parseOptionalInt(editForm.limitMonth),
      status: editForm.status,
    };

    await api.patchResourceLimit(editingId.value, payload);
    ElMessage.success("資源限制已更新");
    showEditDialog.value = false;
    await load();
  } catch (error: any) {
    if (error instanceof Error && !error?.response) {
      ElMessage.error(error.message);
    } else {
      ElMessage.error(error?.response?.data?.detail || "更新資源限制失敗");
    }
  } finally {
    saving.value = false;
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
