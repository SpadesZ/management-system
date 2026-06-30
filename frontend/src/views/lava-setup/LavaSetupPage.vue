<template>
  <div class="lava-page">
    <el-row :gutter="16">
      <el-col :xs="24" :lg="16">
        <el-card class="block">
          <template #header>
            <div class="row">
              <div>
                <div class="title">LAVA Setup</div>
                <div class="hint">對齊 llm_service：Connection / Models / Binding / Test</div>
              </div>
              <div class="actions">
                <el-button @click="loadAll" :loading="loadingConnections || loadingBindings">重新整理</el-button>
                <el-button type="primary" @click="createConnection" :loading="creatingConnection">新增線路</el-button>
                <el-button
                  type="danger"
                  plain
                  @click="deleteCurrentConnection"
                  :disabled="!connectionEditor.id"
                  :loading="deletingConnection"
                >
                  刪除目前線路
                </el-button>
              </div>
            </div>
          </template>

          <el-table :data="connections" v-loading="loadingConnections" @row-click="selectConnection" highlight-current-row>
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="name" label="線路名稱" min-width="140" />
            <el-table-column prop="vendor" label="Vendor" width="130" />
            <el-table-column prop="api_key" label="API Key" width="170" />
            <el-table-column prop="model_name" label="Model" min-width="180" />
            <el-table-column prop="status" label="狀態" width="120" />
          </el-table>

          <el-divider />

          <el-form :model="connectionEditor" label-position="top" class="editor-form">
            <el-row :gutter="12">
              <el-col :xs="24" :md="12">
                <el-form-item label="線路名稱">
                  <el-input v-model="connectionEditor.name" placeholder="例如: OpenRouter-Free-01" />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="6">
                <el-form-item label="Vendor">
                  <el-select v-model="connectionEditor.vendor" placeholder="Vendor">
                    <el-option label="openrouter" value="openrouter" />
                    <el-option label="openai" value="openai" />
                    <el-option label="google" value="google" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="6">
                <el-form-item label="Status">
                  <el-select v-model="connectionEditor.status" placeholder="狀態">
                    <el-option label="draft" value="draft" />
                    <el-option label="active" value="active" />
                    <el-option label="disabled" value="disabled" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="12">
              <el-col :xs="24" :md="14">
                <el-form-item label="Model Name">
                  <el-select
                    v-model="connectionEditor.model_name"
                    filterable
                    allow-create
                    default-first-option
                    clearable
                    placeholder="先點擊 Fetch Models，或直接手動輸入"
                  >
                    <el-option v-for="model in modelOptions" :key="model.id" :label="model.label" :value="model.id" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="10">
                <el-form-item label="API Key（留空=維持原本）">
                  <el-input
                    v-model="connectionEditor.api_key"
                    type="password"
                    show-password
                    placeholder="貼上新的 API Key，儲存後會遮罩"
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <div class="actions">
              <el-button type="primary" @click="saveConnection" :loading="savingConnection" :disabled="!connectionEditor.id">
                儲存線路
              </el-button>
              <el-button @click="fetchModels" :loading="fetchingModels" :disabled="!connectionEditor.id">Fetch Models</el-button>
              <el-button @click="testConnection" :loading="testingConnection" :disabled="!connectionEditor.id">測試線路</el-button>
            </div>

            <el-alert
              v-if="lastPolicy"
              type="warning"
              show-icon
              :closable="false"
              class="policy-alert"
              :title="
                `Nemotron policy: total=${lastPolicy.total_lines}, nemotron=${lastPolicy.nemotron_lines}, max=${lastPolicy.max_nemotron}`
              "
            />
          </el-form>
        </el-card>

        <el-card class="block">
          <template #header>
            <div class="row">
              <div>
                <div class="title">任務綁定</div>
                <div class="hint">僅管理會呼叫 LLM 的任務（模型/線路/Prompt Contract）</div>
              </div>
              <el-button @click="loadBindings" :loading="loadingBindings">重新整理綁定</el-button>
            </div>
          </template>

          <el-table :data="bindings" v-loading="loadingBindings">
            <el-table-column prop="task_id" label="任務代碼" min-width="220" />
            <el-table-column label="任務名稱" min-width="260">
              <template #default="scope">
                {{ scope.row.task_name || scope.row.task_id }}
              </template>
            </el-table-column>
            <el-table-column label="Connection" min-width="240">
              <template #default="scope">
                <el-select
                  v-model="scope.row.connection_id"
                  clearable
                  placeholder="未綁定"
                  :disabled="scope.row.is_locked"
                  @change="onBindingConnectionChange(scope.row)"
                >
                  <el-option v-for="conn in connections" :key="conn.id" :label="`${conn.name} (#${conn.id})`" :value="conn.id" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="Locked" width="120">
              <template #default="scope">
                <el-tag :type="scope.row.is_locked ? 'warning' : 'success'">
                  {{ scope.row.is_locked ? "LOCKED" : "OPEN" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Actions" width="210">
              <template #default="scope">
                <div class="binding-actions">
                  <el-button size="small" @click="toggleBindingLock(scope.row)">
                    {{ scope.row.is_locked ? "Unlock" : "Lock" }}
                  </el-button>
                  <el-button size="small" type="primary" plain @click="testBinding(scope.row)">Test</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card class="block">
          <template #header>
            <div class="title">Runtime Setup</div>
          </template>

          <el-form label-position="top">
            <el-form-item label="CPU Cores">
              <el-select v-model="cpuSelected" :loading="loadingRuntimeCPU">
                <el-option v-for="item in cpuChoices" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <div class="runtime-meta">
                邏輯核心: {{ cpuLimit.logical_cores }} / 有效核心: {{ cpuLimit.effective_cores }}
              </div>
            </el-form-item>

            <el-button type="primary" plain @click="saveRuntimeCPU" :loading="savingRuntimeCPU">套用 CPU 設定</el-button>

            <el-divider />

            <el-form-item label="Flow A Workers">
              <el-select v-model="workerSelected" :loading="loadingRuntimeWorkers">
                <el-option v-for="item in workerChoices" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
              <div class="runtime-meta">目前有效 Worker: {{ effectiveWorkers }}</div>
            </el-form-item>

            <el-button type="primary" plain @click="saveRuntimeWorkers" :loading="savingRuntimeWorkers">
              套用 Worker 設定
            </el-button>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";

import { useLavaSetup } from "./useLavaSetup";

const {
  connections,
  bindings,
  modelOptions,
  lastPolicy,
  connectionEditor,
  loadingConnections,
  loadingBindings,
  creatingConnection,
  savingConnection,
  deletingConnection,
  fetchingModels,
  testingConnection,
  loadingRuntimeCPU,
  savingRuntimeCPU,
  loadingRuntimeWorkers,
  savingRuntimeWorkers,
  cpuChoices,
  cpuSelected,
  cpuLimit,
  workerChoices,
  workerSelected,
  effectiveWorkers,
  loadAll,
  selectConnection,
  createConnection,
  deleteCurrentConnection,
  saveConnection,
  fetchModels,
  testConnection,
  loadBindings,
  onBindingConnectionChange,
  toggleBindingLock,
  testBinding,
  saveRuntimeCPU,
  saveRuntimeWorkers,
} = useLavaSetup();

onMounted(async () => {
  await loadAll();
});
</script>

<style scoped>
.lava-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.block {
  margin-bottom: 16px;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.title {
  font-size: 18px;
  font-weight: 700;
  color: #14345a;
}

.hint {
  font-size: 12px;
  color: #5d7089;
  margin-top: 4px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.editor-form {
  margin-top: 6px;
}

.policy-alert {
  margin-top: 12px;
}

.binding-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.runtime-meta {
  margin-top: 8px;
  color: #5d7089;
  font-size: 12px;
}

@media (max-width: 900px) {
  .binding-actions {
    flex-direction: column;
    align-items: stretch;
    gap: 4px;
  }
}
</style>
