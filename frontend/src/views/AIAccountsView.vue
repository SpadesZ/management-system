<!-- File Path: frontend/src/views/AIAccountsView.vue -->
<!-- Timestamp: 2026-05-30T10:30:00+08:00 -->
<!-- Version: v0.2 -->

<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <div>
          <div class="title">Token 資產盤點 - AI 帳號資產</div>
          <div class="hint">帳號主檔、憑證、授權與歷史紀錄整合管理</div>
        </div>
        <div class="actions">
          <el-button @click="loadAccounts">重新整理</el-button>
        </div>
      </div>
    </template>

    <el-table
      :data="rows"
      v-loading="loading"
      height="340"
      stripe
      highlight-current-row
      :current-row-key="selectedAccountId || undefined"
      @row-click="onSelectAccount"
    >
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column prop="vendor" label="Vendor" width="140" />
      <el-table-column prop="product" label="Product" width="150" />
      <el-table-column prop="plan" label="Plan" width="140" />
      <el-table-column prop="seats" label="Seats" width="90" />
      <el-table-column prop="monthly_cost_usd" label="Monthly Cost" width="140" />
      <el-table-column prop="owner_user_id" label="Owner" width="100" />
      <el-table-column prop="status" label="Status" width="110">
        <template #default="scope">
          <el-tag :type="scope.row.status === 'ACTIVE' ? 'success' : 'warning'">{{ scope.row.status }}</el-tag>
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

    <el-divider />

    <el-empty v-if="!selectedAccount" description="請先在上方選擇 AI 帳號" />

    <div v-else>
      <div class="selected-summary">
        <el-tag type="info">Account #{{ selectedAccount.id }}</el-tag>
        <span>
          {{ selectedAccount.vendor }} / {{ selectedAccount.product }} / {{ selectedAccount.plan }}
        </span>
      </div>

      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="Credential 憑證" name="credentials">
          <div class="tab-actions">
            <el-button @click="loadCredentials">重新整理</el-button>
            <el-button type="primary" @click="showCreateCredentialDialog = true">新增憑證</el-button>
          </div>

          <el-table :data="credentials" v-loading="credentialLoading" height="280" stripe>
            <el-table-column prop="id" label="ID" width="90" />
            <el-table-column prop="credential_name" label="Name" min-width="180" />
            <el-table-column prop="credential_type" label="Type" width="120" />
            <el-table-column prop="masked_secret" label="Masked Secret" min-width="180" />
            <el-table-column prop="status" label="Status" width="110" />
            <el-table-column prop="last_rotated_at" label="Last Rotated" min-width="180" />
            <el-table-column prop="expires_at" label="Expires At" min-width="180" />
            <el-table-column label="Actions" width="220" fixed="right">
              <template #default="scope">
                <el-button size="small" type="primary" plain @click="rotateCredential(scope.row)">輪替</el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="scope.row.status === 'DISABLED'"
                  @click="disableCredential(scope.row)"
                >
                  停用
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="Access Grants 授權" name="grants">
          <div class="tab-actions">
            <el-button @click="loadAccessGrants">重新整理</el-button>
            <el-button type="primary" @click="showCreateGrantDialog = true">新增授權</el-button>
          </div>

          <el-table :data="grants" v-loading="grantLoading" height="280" stripe>
            <el-table-column prop="id" label="ID" width="90" />
            <el-table-column prop="user_id" label="User ID" width="100" />
            <el-table-column prop="status" label="Status" width="110" />
            <el-table-column prop="grant_reason" label="Grant Reason" min-width="200" />
            <el-table-column prop="granted_by_user_id" label="Granted By" width="110" />
            <el-table-column prop="granted_at" label="Granted At" min-width="180" />
            <el-table-column prop="revoked_at" label="Revoked At" min-width="180" />
            <el-table-column label="Actions" width="120" fixed="right">
              <template #default="scope">
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="scope.row.status !== 'ACTIVE'"
                  @click="revokeGrant(scope.row)"
                >
                  撤銷
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="History 歷史" name="history">
          <div class="tab-actions">
            <el-input v-model="historyEventType" placeholder="事件類型（例如 ACCESS_GRANT）" clearable style="width: 280px" />
            <el-button @click="loadHistory">查詢</el-button>
            <el-button @click="resetHistoryFilter">清除</el-button>
          </div>

          <el-table :data="historyRows" v-loading="historyLoading" height="280" stripe>
            <el-table-column prop="id" label="ID" width="90" />
            <el-table-column prop="event_type" label="Event Type" width="180" />
            <el-table-column prop="actor_user_id" label="Actor" width="90" />
            <el-table-column prop="event_time" label="Time" min-width="180" />
            <el-table-column label="Detail" min-width="300" show-overflow-tooltip>
              <template #default="scope">
                {{ toJsonText(scope.row.detail_json) }}
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-card>

  <el-dialog v-model="showCreateCredentialDialog" title="新增憑證" width="560px">
    <el-form label-width="130px">
      <el-form-item label="Credential Name">
        <el-input v-model="credentialForm.credentialName" maxlength="120" />
      </el-form-item>
      <el-form-item label="Credential Type">
        <el-select v-model="credentialForm.credentialType" style="width: 100%">
          <el-option label="PASSWORD" value="PASSWORD" />
          <el-option label="TOKEN" value="TOKEN" />
          <el-option label="COOKIE" value="COOKIE" />
          <el-option label="OTHER" value="OTHER" />
        </el-select>
      </el-form-item>
      <el-form-item label="Plain Secret">
        <el-input v-model="credentialForm.plainSecret" show-password />
      </el-form-item>
      <el-form-item label="Expires At">
        <el-date-picker
          v-model="credentialForm.expiresAt"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss[Z]"
          clearable
          style="width: 100%"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="showCreateCredentialDialog = false">取消</el-button>
      <el-button type="primary" :loading="credentialSubmitting" @click="createCredential">建立</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="showCreateGrantDialog" title="新增授權" width="560px">
    <el-form label-width="130px">
      <el-form-item label="User">
        <el-select v-model="grantForm.userId" filterable style="width: 100%" placeholder="選擇使用者">
          <el-option v-for="user in users" :key="user.id" :label="`${user.id} - ${user.name} (${user.email})`" :value="user.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="Grant Reason">
        <el-input v-model="grantForm.grantReason" type="textarea" :rows="3" maxlength="1000" show-word-limit />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="showCreateGrantDialog = false">取消</el-button>
      <el-button type="primary" :loading="grantSubmitting" @click="createGrant">建立</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { api } from "../api/endpoints";

interface AIAccountItem {
  id: number;
  vendor: string;
  product: string;
  plan: string;
  seats: number;
  monthly_cost_usd: string;
  renewal_date: string | null;
  owner_user_id: number;
  status: string;
}

interface CredentialItem {
  id: number;
  ai_account_id: number;
  credential_name: string;
  credential_type: string;
  masked_secret: string;
  status: string;
  expires_at: string | null;
  last_rotated_at: string | null;
  created_by_user_id: number | null;
}

interface AccessGrantItem {
  id: number;
  ai_account_id: number;
  user_id: number;
  granted_by_user_id: number | null;
  grant_reason: string | null;
  status: string;
  granted_at: string;
  revoked_by_user_id: number | null;
  revoke_reason: string | null;
  revoked_at: string | null;
}

interface HistoryItem {
  id: number;
  ai_account_id: number;
  event_type: string;
  actor_user_id: number | null;
  event_time: string;
  detail_json: Record<string, unknown>;
}

interface UserItem {
  id: number;
  name: string;
  email: string;
}

const rows = ref<AIAccountItem[]>([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const selectedAccountId = ref<number | null>(null);
const selectedAccount = ref<AIAccountItem | null>(null);
const activeTab = ref("credentials");

const credentials = ref<CredentialItem[]>([]);
const grants = ref<AccessGrantItem[]>([]);
const historyRows = ref<HistoryItem[]>([]);
const users = ref<UserItem[]>([]);

const credentialLoading = ref(false);
const grantLoading = ref(false);
const historyLoading = ref(false);

const showCreateCredentialDialog = ref(false);
const credentialSubmitting = ref(false);
const credentialForm = reactive({
  credentialName: "",
  credentialType: "PASSWORD",
  plainSecret: "",
  expiresAt: "",
});

const showCreateGrantDialog = ref(false);
const grantSubmitting = ref(false);
const grantForm = reactive({
  userId: undefined as number | undefined,
  grantReason: "",
});

const historyEventType = ref("");

const toJsonText = (value: Record<string, unknown> | null | undefined): string => {
  if (!value) {
    return "{}";
  }
  try {
    return JSON.stringify(value);
  } catch {
    return "{}";
  }
};

const selectAccountById = (accountId: number | null): void => {
  selectedAccountId.value = accountId;
  if (accountId === null) {
    selectedAccount.value = null;
    return;
  }
  selectedAccount.value = rows.value.find((item) => item.id === accountId) || null;
};

const ensureSelectedAccount = (): number | null => {
  if (!selectedAccount.value) {
    ElMessage.warning("請先選擇 AI 帳號");
    return null;
  }
  return selectedAccount.value.id;
};

const loadUsers = async (): Promise<void> => {
  try {
    const { data } = await api.users({ page: 1, page_size: 200, sort_by: "id", sort_order: "asc" });
    users.value = Array.isArray(data?.items) ? data.items : [];
  } catch {
    users.value = [];
  }
};

const loadAccounts = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.aiAccounts({
      page: page.value,
      page_size: pageSize.value,
      sort_by: "id",
      sort_order: "desc",
    });
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);

    if (rows.value.length === 0) {
      selectAccountById(null);
      credentials.value = [];
      grants.value = [];
      historyRows.value = [];
      return;
    }

    if (selectedAccountId.value === null || !rows.value.some((item) => item.id === selectedAccountId.value)) {
      selectAccountById(rows.value[0].id);
    } else {
      selectAccountById(selectedAccountId.value);
    }

    await loadCurrentTabData();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入 AI 帳號失敗");
  } finally {
    loading.value = false;
  }
};

const loadCredentials = async (): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }
  credentialLoading.value = true;
  try {
    const { data } = await api.aiAccountCredentials(accountId, {
      page: 1,
      page_size: 200,
      sort_by: "created_at",
      sort_order: "desc",
    });
    credentials.value = Array.isArray(data?.items) ? data.items : [];
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入憑證失敗");
  } finally {
    credentialLoading.value = false;
  }
};

const loadAccessGrants = async (): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }
  grantLoading.value = true;
  try {
    const { data } = await api.aiAccountAccessGrants(accountId, {
      page: 1,
      page_size: 200,
      sort_by: "granted_at",
      sort_order: "desc",
    });
    grants.value = Array.isArray(data?.items) ? data.items : [];
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入授權失敗");
  } finally {
    grantLoading.value = false;
  }
};

const loadHistory = async (): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }
  historyLoading.value = true;
  try {
    const params: Record<string, unknown> = {
      page: 1,
      page_size: 200,
      sort_by: "event_time",
      sort_order: "desc",
    };
    const normalizedType = historyEventType.value.trim().toUpperCase();
    if (normalizedType) {
      params.event_type = normalizedType;
    }
    const { data } = await api.aiAccountHistory(accountId, params);
    historyRows.value = Array.isArray(data?.items) ? data.items : [];
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入歷史紀錄失敗");
  } finally {
    historyLoading.value = false;
  }
};

const loadCurrentTabData = async (): Promise<void> => {
  if (activeTab.value === "credentials") {
    await loadCredentials();
    return;
  }
  if (activeTab.value === "grants") {
    await loadAccessGrants();
    return;
  }
  await loadHistory();
};

const onPageChange = async (nextPage: number): Promise<void> => {
  page.value = nextPage;
  await loadAccounts();
};

const onSelectAccount = async (row: AIAccountItem): Promise<void> => {
  if (!row || selectedAccountId.value === row.id) {
    return;
  }
  selectAccountById(row.id);
  await loadCurrentTabData();
};

const onTabChange = async (): Promise<void> => {
  await loadCurrentTabData();
};

const resetCredentialForm = (): void => {
  credentialForm.credentialName = "";
  credentialForm.credentialType = "PASSWORD";
  credentialForm.plainSecret = "";
  credentialForm.expiresAt = "";
};

const createCredential = async (): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }
  const credentialName = credentialForm.credentialName.trim();
  const plainSecret = credentialForm.plainSecret;
  if (!credentialName || !plainSecret) {
    ElMessage.warning("Credential Name 與 Plain Secret 為必填");
    return;
  }

  credentialSubmitting.value = true;
  try {
    const payload: Record<string, unknown> = {
      credential_name: credentialName,
      credential_type: credentialForm.credentialType,
      plain_secret: plainSecret,
    };
    if (credentialForm.expiresAt) {
      payload.expires_at = credentialForm.expiresAt;
    }
    await api.createAiAccountCredential(accountId, payload);
    ElMessage.success("憑證建立成功");
    showCreateCredentialDialog.value = false;
    resetCredentialForm();
    await loadCredentials();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "建立憑證失敗");
  } finally {
    credentialSubmitting.value = false;
  }
};

const rotateCredential = async (row: CredentialItem): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }

  try {
    const result = await ElMessageBox.prompt("請輸入新的 Plain Secret", `輪替憑證 #${row.id}`, {
      confirmButtonText: "輪替",
      cancelButtonText: "取消",
      inputType: "password",
      inputValidator: (value: string) => {
        if (!value || value.length < 4) {
          return "長度至少 4 字元";
        }
        return true;
      },
    });

    await api.rotateAiAccountCredential(accountId, row.id, { new_plain_secret: result.value });
    ElMessage.success("憑證輪替成功");
    await loadCredentials();
  } catch (error: any) {
    if (error === "cancel" || error === "close") {
      return;
    }
    ElMessage.error(error?.response?.data?.detail || "輪替憑證失敗");
  }
};

const disableCredential = async (row: CredentialItem): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }
  try {
    await ElMessageBox.confirm(`確認停用憑證 #${row.id} 嗎？`, "停用憑證", {
      confirmButtonText: "停用",
      cancelButtonText: "取消",
      type: "warning",
    });
    await api.disableAiAccountCredential(accountId, row.id);
    ElMessage.success("憑證已停用");
    await loadCredentials();
  } catch (error: any) {
    if (error === "cancel" || error === "close") {
      return;
    }
    ElMessage.error(error?.response?.data?.detail || "停用憑證失敗");
  }
};

const resetGrantForm = (): void => {
  grantForm.userId = undefined;
  grantForm.grantReason = "";
};

const createGrant = async (): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }
  if (!grantForm.userId) {
    ElMessage.warning("請選擇授權使用者");
    return;
  }

  grantSubmitting.value = true;
  try {
    await api.createAiAccountAccessGrant(accountId, {
      user_id: grantForm.userId,
      grant_reason: grantForm.grantReason.trim() || null,
    });
    ElMessage.success("授權建立成功");
    showCreateGrantDialog.value = false;
    resetGrantForm();
    await loadAccessGrants();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "建立授權失敗");
  } finally {
    grantSubmitting.value = false;
  }
};

const revokeGrant = async (row: AccessGrantItem): Promise<void> => {
  const accountId = ensureSelectedAccount();
  if (accountId === null) {
    return;
  }
  try {
    const result = await ElMessageBox.prompt("請輸入撤銷理由", `撤銷授權 #${row.id}`, {
      confirmButtonText: "撤銷",
      cancelButtonText: "取消",
      inputValidator: (value: string) => {
        if (!value || !value.trim()) {
          return "撤銷理由必填";
        }
        return true;
      },
    });
    await api.revokeAiAccountAccessGrant(accountId, row.id, { revoke_reason: result.value.trim() });
    ElMessage.success("授權已撤銷");
    await loadAccessGrants();
  } catch (error: any) {
    if (error === "cancel" || error === "close") {
      return;
    }
    ElMessage.error(error?.response?.data?.detail || "撤銷授權失敗");
  }
};

const resetHistoryFilter = async (): Promise<void> => {
  historyEventType.value = "";
  await loadHistory();
};

onMounted(async () => {
  await Promise.all([loadUsers(), loadAccounts()]);
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

.selected-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  color: #355272;
  font-size: 14px;
}

.tab-actions {
  margin-bottom: 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 900px) {
  .header-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
