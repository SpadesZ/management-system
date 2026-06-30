<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <div>
          <div class="title">Token 支出財務</div>
          <div class="hint">資產合約與訂閱治理（月付 / 年付 / 用量計費）</div>
        </div>
        <div class="actions">
          <el-button @click="load">重新整理</el-button>
          <el-button type="primary" @click="showCreateDialog = true">新增合約</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column label="資產" min-width="160">
        <template #default="scope">{{ assetLabel(scope.row) }}</template>
      </el-table-column>
      <el-table-column prop="billing_cycle" label="Billing" width="130" />
      <el-table-column prop="monthly_fee_usd" label="Monthly Fee" width="140" />
      <el-table-column prop="yearly_fee_usd" label="Yearly Fee" width="140" />
      <el-table-column prop="monthly_amortized_usd" label="月攤提" width="130" />
      <el-table-column prop="start_date" label="開始日" width="120" />
      <el-table-column prop="end_date" label="到期日" width="120" />
      <el-table-column prop="auto_renew" label="自動續約" width="110">
        <template #default="scope">
          <el-tag :type="scope.row.auto_renew ? 'success' : 'info'">{{ scope.row.auto_renew ? "是" : "否" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="狀態" width="120">
        <template #default="scope">
          <el-tag :type="scope.row.status === 'ACTIVE' ? 'success' : 'warning'">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="payment_method" label="付款方式" width="140" />
      <el-table-column prop="notes" label="備註" min-width="180" show-overflow-tooltip />
      <el-table-column label="Actions" min-width="150" fixed="right">
        <template #default="scope">
          <el-button size="small" plain @click="toggleContractStatus(scope.row)">
            {{ scope.row.status === "ACTIVE" ? "封存" : "啟用" }}
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

  <el-dialog v-model="showCreateDialog" title="新增資產合約" width="720px">
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

      <el-form-item label="Billing Cycle">
        <el-select v-model="createForm.billingCycle" style="width: 100%">
          <el-option label="MONTHLY" value="MONTHLY" />
          <el-option label="YEARLY" value="YEARLY" />
          <el-option label="USAGE_BASED" value="USAGE_BASED" />
        </el-select>
      </el-form-item>

      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="Monthly Fee USD">
            <el-input
              v-model="createForm.monthlyFeeUsd"
              placeholder="例如 99.000000（月付需填）"
              :disabled="createForm.billingCycle !== 'MONTHLY'"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="Yearly Fee USD">
            <el-input
              v-model="createForm.yearlyFeeUsd"
              placeholder="例如 999.000000（年付需填）"
              :disabled="createForm.billingCycle !== 'YEARLY'"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="開始日">
            <el-date-picker
              v-model="createForm.startDate"
              type="date"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="到期日">
            <el-date-picker
              v-model="createForm.endDate"
              type="date"
              value-format="YYYY-MM-DD"
              clearable
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-row :gutter="12">
        <el-col :xs="24" :md="12">
          <el-form-item label="付款方式">
            <el-input v-model="createForm.paymentMethod" placeholder="例如 公司信用卡" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-form-item label="狀態">
            <el-select v-model="createForm.status" style="width: 100%">
              <el-option label="ACTIVE" value="ACTIVE" />
              <el-option label="INACTIVE" value="INACTIVE" />
              <el-option label="ARCHIVED" value="ARCHIVED" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="自動續約">
        <el-switch v-model="createForm.autoRenew" />
      </el-form-item>

      <el-form-item label="備註">
        <el-input v-model="createForm.notes" type="textarea" :rows="3" maxlength="1000" show-word-limit />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="showCreateDialog = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="createContract">建立</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

type BillingCycle = "MONTHLY" | "YEARLY" | "USAGE_BASED";

interface AssetContractItem {
  id: number;
  api_key_id: number | null;
  ai_account_id: number | null;
  billing_cycle: BillingCycle;
  monthly_fee_usd: string | null;
  yearly_fee_usd: string | null;
  monthly_amortized_usd: string;
  currency: string;
  start_date: string;
  end_date: string | null;
  auto_renew: boolean;
  payment_method: string | null;
  status: string;
  notes: string | null;
}

const rows = ref<AssetContractItem[]>([]);
const loading = ref(false);
const creating = ref(false);
const showCreateDialog = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const createForm = reactive({
  assetType: "API_KEY",
  assetId: undefined as number | undefined,
  billingCycle: "MONTHLY" as BillingCycle,
  monthlyFeeUsd: "",
  yearlyFeeUsd: "",
  startDate: "",
  endDate: "",
  autoRenew: false,
  paymentMethod: "",
  status: "ACTIVE",
  notes: "",
});

const assetLabel = (row: AssetContractItem): string => {
  if (row.api_key_id !== null) {
    return `API_KEY:${row.api_key_id}`;
  }
  if (row.ai_account_id !== null) {
    return `AI_ACCOUNT:${row.ai_account_id}`;
  }
  return "-";
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.assetContracts({
      page: page.value,
      page_size: pageSize.value,
      sort_by: "created_at",
      sort_order: "desc",
    });
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入資產合約失敗");
  } finally {
    loading.value = false;
  }
};

const onPageChange = async (nextPage: number): Promise<void> => {
  page.value = nextPage;
  await load();
};

const resetCreateForm = (): void => {
  createForm.assetType = "API_KEY";
  createForm.assetId = undefined;
  createForm.billingCycle = "MONTHLY";
  createForm.monthlyFeeUsd = "";
  createForm.yearlyFeeUsd = "";
  createForm.startDate = "";
  createForm.endDate = "";
  createForm.autoRenew = false;
  createForm.paymentMethod = "";
  createForm.status = "ACTIVE";
  createForm.notes = "";
};

const createContract = async (): Promise<void> => {
  if (!createForm.assetId) {
    ElMessage.warning("請輸入資產 ID");
    return;
  }
  if (!createForm.startDate) {
    ElMessage.warning("請選擇開始日");
    return;
  }
  if (createForm.billingCycle === "MONTHLY" && !createForm.monthlyFeeUsd.trim()) {
    ElMessage.warning("MONTHLY 合約需填 Monthly Fee USD");
    return;
  }
  if (createForm.billingCycle === "YEARLY" && !createForm.yearlyFeeUsd.trim()) {
    ElMessage.warning("YEARLY 合約需填 Yearly Fee USD");
    return;
  }

  creating.value = true;
  try {
    const payload: Record<string, unknown> = {
      billing_cycle: createForm.billingCycle,
      currency: "USD",
      start_date: createForm.startDate,
      end_date: createForm.endDate || null,
      auto_renew: createForm.autoRenew,
      payment_method: createForm.paymentMethod.trim() || null,
      status: createForm.status,
      notes: createForm.notes.trim() || null,
    };

    if (createForm.assetType === "API_KEY") {
      payload.api_key_id = createForm.assetId;
    } else {
      payload.ai_account_id = createForm.assetId;
    }

    if (createForm.billingCycle === "MONTHLY") {
      payload.monthly_fee_usd = createForm.monthlyFeeUsd.trim();
    } else if (createForm.billingCycle === "YEARLY") {
      payload.yearly_fee_usd = createForm.yearlyFeeUsd.trim();
    }

    await api.createAssetContract(payload);
    ElMessage.success("資產合約建立成功");
    showCreateDialog.value = false;
    resetCreateForm();
    page.value = 1;
    await load();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "建立資產合約失敗");
  } finally {
    creating.value = false;
  }
};

const toggleContractStatus = async (row: AssetContractItem): Promise<void> => {
  const nextStatus = row.status === "ACTIVE" ? "ARCHIVED" : "ACTIVE";
  try {
    await api.patchAssetContract(row.id, { status: nextStatus });
    ElMessage.success(`合約狀態已更新為 ${nextStatus}`);
    await load();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "更新合約狀態失敗");
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
