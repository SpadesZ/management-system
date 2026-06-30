<!-- File Path: frontend/src/views/UsagePurposesView.vue -->
<!-- Timestamp: 2026-05-26T13:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <div>
          <div class="title">Usage Purposes</div>
          <div class="hint">管理 ROI 使用目的主檔（Phase 2）</div>
        </div>
        <div class="actions">
          <el-button @click="load">重新整理</el-button>
          <el-button type="primary" :disabled="!canManage" @click="showCreateDialog = true">新增 Purpose</el-button>
        </div>
      </div>
    </template>

    <el-alert
      v-if="!canManage"
      type="info"
      show-icon
      :closable="false"
      title="目前角色僅可查詢；建立 Purpose 需 ADMIN 或 FINANCE 權限"
      class="role-alert"
    />

    <el-table :data="rows" v-loading="loading" height="560" stripe>
      <el-table-column prop="id" label="ID" width="90" />
      <el-table-column prop="code" label="Code" min-width="180" />
      <el-table-column prop="name" label="Name" min-width="200" />
      <el-table-column prop="description" label="Description" min-width="260" show-overflow-tooltip />
      <el-table-column prop="status" label="Status" width="130">
        <template #default="scope">
          <el-tag :type="scope.row.status === 'ACTIVE' ? 'success' : 'info'">{{ scope.row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_by_user_id" label="Created By" width="120" />
      <el-table-column prop="created_at" label="Created At" min-width="180" />
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

  <el-dialog v-model="showCreateDialog" title="新增 Usage Purpose" width="560px">
    <el-form label-width="120px">
      <el-form-item label="Code">
        <el-input v-model="createForm.code" placeholder="例如 ROI_KNOWLEDGE_BASE" />
      </el-form-item>
      <el-form-item label="Name">
        <el-input v-model="createForm.name" placeholder="例如 內部知識萃取" />
      </el-form-item>
      <el-form-item label="Status">
        <el-select v-model="createForm.status" style="width: 100%">
          <el-option label="ACTIVE" value="ACTIVE" />
          <el-option label="INACTIVE" value="INACTIVE" />
        </el-select>
      </el-form-item>
      <el-form-item label="Description">
        <el-input v-model="createForm.description" type="textarea" :rows="4" maxlength="4000" show-word-limit />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="showCreateDialog = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="createPurpose">建立</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

interface UsagePurposeItem {
  id: number;
  code: string;
  name: string;
  description: string | null;
  status: string;
  created_by_user_id: number | null;
  created_at: string;
}

const rows = ref<UsagePurposeItem[]>([]);
const loading = ref(false);
const submitting = ref(false);
const showCreateDialog = ref(false);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const myRole = ref("");

const createForm = reactive({
  code: "",
  name: "",
  status: "ACTIVE",
  description: "",
});

const canManage = computed(() => {
  return new Set(["ADMIN", "FINANCE"]).has(myRole.value);
});

const loadMe = async (): Promise<void> => {
  try {
    const { data } = await api.me();
    myRole.value = String(data?.role || "").toUpperCase();
  } catch {
    myRole.value = "";
  }
};

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const { data } = await api.usagePurposes({
      page: page.value,
      page_size: pageSize.value,
      sort_by: "created_at",
      sort_order: "desc",
    });
    rows.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入 usage purposes 失敗");
  } finally {
    loading.value = false;
  }
};

const resetCreateForm = (): void => {
  createForm.code = "";
  createForm.name = "";
  createForm.status = "ACTIVE";
  createForm.description = "";
};

const createPurpose = async (): Promise<void> => {
  const code = createForm.code.trim();
  const name = createForm.name.trim();
  if (!code || !name) {
    ElMessage.warning("Code 與 Name 為必填");
    return;
  }

  submitting.value = true;
  try {
    await api.createUsagePurpose({
      code,
      name,
      status: createForm.status,
      description: createForm.description.trim() || null,
    });
    ElMessage.success("Usage purpose 建立成功");
    showCreateDialog.value = false;
    resetCreateForm();
    page.value = 1;
    await load();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "建立 usage purpose 失敗");
  } finally {
    submitting.value = false;
  }
};

const onPageChange = async (nextPage: number): Promise<void> => {
  page.value = nextPage;
  await load();
};

onMounted(async () => {
  await loadMe();
  await load();
});
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

.role-alert {
  margin-bottom: 10px;
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
