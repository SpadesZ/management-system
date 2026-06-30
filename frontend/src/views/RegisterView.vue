<!-- File Path: frontend/src/views/RegisterView.vue -->
<!-- Timestamp: 2026-05-26T00:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <div class="register-page">
    <el-card class="register-card">
      <template #header>
        <div class="header">註冊新帳號</div>
      </template>

      <el-form :model="form" label-position="top" @submit.prevent="handleRegister">
        <el-form-item label="姓名">
          <el-input v-model="form.name" placeholder="請輸入姓名" />
        </el-form-item>

        <el-form-item label="Email">
          <el-input v-model="form.email" placeholder="name@example.com" />
        </el-form-item>

        <el-form-item label="密碼">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 8 碼" />
        </el-form-item>

        <el-form-item label="確認密碼">
          <el-input v-model="form.confirmPassword" type="password" show-password placeholder="再次輸入密碼" />
        </el-form-item>

        <el-form-item label="部門">
          <el-select v-model="form.department_id" clearable placeholder="不選則使用預設部門" style="width: 100%">
            <el-option
              v-for="dept in departments"
              :key="dept.id"
              :label="`${dept.name} (#${dept.id})`"
              :value="dept.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="員工編號（選填）">
          <el-input v-model="form.employee_no" placeholder="不填將由系統自動產生" />
        </el-form-item>

        <el-form-item>
          <div class="actions">
            <el-button type="primary" :loading="loading" @click="handleRegister" style="width: 100%">
              建立帳號
            </el-button>
            <el-button @click="goLogin" style="width: 100%">返回登入</el-button>
          </div>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { api } from "../api/endpoints";

interface DepartmentOption {
  id: number;
  name: string;
}

const router = useRouter();
const loading = ref(false);
const departments = ref<DepartmentOption[]>([]);

const form = reactive({
  name: "",
  email: "",
  password: "",
  confirmPassword: "",
  department_id: undefined as number | undefined,
  employee_no: "",
});

const goLogin = (): void => {
  router.push("/login");
};

const loadOptions = async (): Promise<void> => {
  try {
    const { data } = await api.registerOptions();
    departments.value = (data.departments || []) as DepartmentOption[];
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入註冊選項失敗");
  }
};

const handleRegister = async (): Promise<void> => {
  if (!form.name || !form.email || !form.password || !form.confirmPassword) {
    ElMessage.error("請完整填寫註冊資訊");
    return;
  }

  if (form.password !== form.confirmPassword) {
    ElMessage.error("兩次密碼不一致");
    return;
  }

  loading.value = true;
  try {
    const payload: Record<string, unknown> = {
      name: form.name,
      email: form.email,
      password: form.password,
    };

    if (form.department_id !== undefined) {
      payload.department_id = form.department_id;
    }
    if (form.employee_no.trim()) {
      payload.employee_no = form.employee_no.trim();
    }

    const { data } = await api.registerAccount(payload);
    ElMessage.success(data?.message || "註冊成功，請登入");
    router.push("/login");
  } catch (error: any) {
    const message = error?.response?.data?.detail?.message || error?.response?.data?.detail || "註冊失敗";
    ElMessage.error(message);
  } finally {
    loading.value = false;
  }
};

onMounted(loadOptions);
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top left, #dfeeff 0%, #cfe3fb 30%, #a8c8ef 100%);
  padding: 18px;
}

.register-card {
  width: min(500px, 96vw);
  border-radius: 16px;
}

.header {
  font-size: 20px;
  font-weight: 700;
  color: #1b365d;
}

.actions {
  display: grid;
  gap: 8px;
  width: 100%;
}
</style>
