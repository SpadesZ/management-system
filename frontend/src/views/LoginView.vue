<!-- File Path: frontend/src/views/LoginView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <div class="login-page">
    <el-card class="login-card">
      <template #header>
        <div class="header">LLM FinOps 登入</div>
      </template>

      <el-form :model="form" label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="Email">
          <el-input v-model="form.email" placeholder="admin@example.com" />
        </el-form-item>
        <el-form-item label="Password">
          <el-input v-model="form.password" type="password" show-password placeholder="••••••••" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="handleLogin" style="width: 100%">
            登入
          </el-button>
        </el-form-item>
        <el-form-item>
          <el-button plain @click="goRegister" style="width: 100%">註冊新帳號</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { api } from "../api/endpoints";

const router = useRouter();
const loading = ref(false);

const form = reactive({
  email: "admin@example.com",
  password: "ChangeThisPassword!",
});

const goRegister = (): void => {
  router.push("/register");
};

const handleLogin = async (): Promise<void> => {
  if (!form.email || !form.password) {
    ElMessage.error("請輸入帳號密碼");
    return;
  }

  loading.value = true;
  try {
    const { data } = await api.login(form.email, form.password);
    localStorage.setItem("access_token", data.access_token);
    ElMessage.success("登入成功");
    router.push("/dashboard");
  } catch (error: any) {
    const message = error?.response?.data?.detail?.message || "登入失敗";
    ElMessage.error(message);
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top right, #e3f1ff 0%, #d5e8ff 30%, #adcdf4 100%);
}

.login-card {
  width: min(420px, 90vw);
  border-radius: 16px;
}

.header {
  font-size: 20px;
  font-weight: 700;
  color: #1b365d;
}
</style>
