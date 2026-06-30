<!-- File Path: frontend/src/views/AssistantView.vue -->
<!-- Timestamp: 2026-05-26T13:00:00+08:00 -->
<!-- Version: v0.2 -->

<template>
  <div class="assistant-page">
    <el-row :gutter="16">
      <el-col :xs="24" :lg="16">
        <el-card class="chat-card">
          <template #header>
            <div class="header-row">
              <div>
                <div class="title">Ask FinOps</div>
                <div class="hint">只讀助理：問答、異常解釋、審批摘要、月報草稿、節省建議</div>
              </div>
            </div>
          </template>

          <div ref="chatBodyRef" class="chat-body">
            <div v-for="(item, index) in chatItems" :key="`${item.role}-${index}-${item.createdAt}`" class="chat-row">
              <div :class="['bubble', item.role === 'user' ? 'bubble-user' : 'bubble-assistant']">
                <div class="meta">{{ item.role === "user" ? "你" : "Ask FinOps" }}</div>
                <div class="content">{{ item.content }}</div>
              </div>
            </div>
          </div>

          <div class="composer">
            <el-row :gutter="8">
              <el-col :xs="24" :md="8">
                <el-form-item label="Context Type">
                  <el-select v-model="form.context_type" style="width: 100%">
                    <el-option label="auto" value="auto" />
                    <el-option label="costs" value="costs" />
                    <el-option label="usage" value="usage" />
                    <el-option label="alerts" value="alerts" />
                    <el-option label="approval_request" value="approval_request" />
                    <el-option label="policy" value="policy" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="8">
                <el-form-item label="Context ID（選填）">
                  <el-input v-model="form.context_id" placeholder="例如 approval request id" />
                </el-form-item>
              </el-col>
              <el-col :xs="24" :md="8">
                <el-form-item label="Session ID">
                  <el-input v-model="form.session_id" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-input
              v-model="form.message"
              type="textarea"
              :rows="4"
              placeholder="例如：這個月哪個部門成本異常？幫我分析原因與下一步"
              @keydown.ctrl.enter.prevent="sendMessage"
            />

            <div class="composer-actions">
              <el-button type="primary" :loading="loading" @click="sendMessage">送出（Ctrl+Enter）</el-button>
              <el-button :disabled="loading" @click="clearChat">清空對話</el-button>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card class="meta-card">
          <template #header>
            <div class="title">回應資訊</div>
          </template>

          <div v-if="lastResponse">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="Primary Task">
                {{ lastResponse.primary_task_id }}
              </el-descriptions-item>
              <el-descriptions-item label="Risk Level">
                <el-tag :type="riskTagType">{{ lastResponse.risk_level }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="Trace ID">
                {{ lastResponse.trace_id }}
              </el-descriptions-item>
              <el-descriptions-item label="Conversation ID">
                {{ lastResponse.conversation_id ?? "-" }}
              </el-descriptions-item>
            </el-descriptions>

            <div class="section">
              <div class="section-title">Task IDs</div>
              <el-tag v-for="task in lastResponse.task_ids" :key="task" class="task-tag" type="info" effect="plain">
                {{ task }}
              </el-tag>
            </div>

            <div class="section">
              <div class="section-title">Sources</div>
              <el-empty v-if="lastResponse.sources.length === 0" description="無來源資訊" :image-size="48" />
              <div v-else class="source-list">
                <div v-for="source in lastResponse.sources" :key="`${source.source_key}-${source.source_id || ''}`" class="source-item">
                  <div class="source-key">{{ source.source_key }}</div>
                  <div class="source-label">{{ source.source_label }}</div>
                  <div class="source-meta">id: {{ source.source_id || "-" }} / scope: {{ source.scope_checked ? "checked" : "n/a" }}</div>
                </div>
              </div>
            </div>

            <div class="section">
              <div class="section-title">Suggested Actions</div>
              <el-empty v-if="lastResponse.suggested_actions.length === 0" description="無建議動作" :image-size="48" />
              <div v-else class="action-list">
                <el-button
                  v-for="(action, idx) in lastResponse.suggested_actions"
                  :key="`${action.action_type}-${action.target || ''}-${idx}`"
                  size="small"
                  plain
                  @click="runSuggestedAction(action)"
                >
                  {{ action.label }}
                </el-button>
              </div>
            </div>

            <div class="section">
              <div class="section-title">History</div>
              <el-button size="small" plain @click="goToHistory">前往 Assistant History</el-button>
            </div>
          </div>

          <el-empty v-else description="送出第一個問題後會顯示回應資訊" :image-size="72" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { api } from "../api/endpoints";

interface AssistantSource {
  source_key: string;
  source_label: string;
  source_id?: string;
  scope_checked: boolean;
}

interface AssistantAction {
  action_type: string;
  label: string;
  target?: string;
}

interface AssistantResponse {
  answer: string;
  primary_task_id: string;
  task_ids: string[];
  sources: AssistantSource[];
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "BLOCKED";
  suggested_actions: AssistantAction[];
  trace_id: string;
  conversation_id?: number;
}

interface ChatItem {
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

const router = useRouter();
const chatBodyRef = ref<HTMLDivElement | null>(null);

const loading = ref(false);
const lastResponse = ref<AssistantResponse | null>(null);
const lastUserMessage = ref("");

const chatItems = ref<ChatItem[]>([
  {
    role: "assistant",
    content: "你好，我是 Ask FinOps。你可以問我成本異常、政策問答、審批摘要、月報草稿與 token 節省建議。",
    createdAt: new Date().toISOString(),
  },
]);

const form = reactive({
  message: "",
  context_type: "auto",
  context_id: "",
  session_id: `assistant-${Date.now()}`,
});

const riskTagType = computed(() => {
  const risk = lastResponse.value?.risk_level;
  if (risk === "BLOCKED") {
    return "danger";
  }
  if (risk === "HIGH") {
    return "warning";
  }
  if (risk === "MEDIUM") {
    return "info";
  }
  return "success";
});

const scrollToBottom = async (): Promise<void> => {
  await nextTick();
  if (!chatBodyRef.value) {
    return;
  }
  chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight;
};

const clearChat = (): void => {
  chatItems.value = [
    {
      role: "assistant",
      content: "對話已清空，你可以繼續提問 FinOps 相關問題。",
      createdAt: new Date().toISOString(),
    },
  ];
  lastResponse.value = null;
  lastUserMessage.value = "";
};

const sendMessage = async (): Promise<void> => {
  const message = form.message.trim();
  if (!message) {
    ElMessage.warning("請先輸入問題");
    return;
  }

  loading.value = true;
  lastUserMessage.value = message;
  chatItems.value.push({ role: "user", content: message, createdAt: new Date().toISOString() });
  await scrollToBottom();

  try {
    const payload: Record<string, unknown> = {
      message,
      context_type: form.context_type,
      session_id: form.session_id,
    };
    if (form.context_id.trim()) {
      payload.context_id = form.context_id.trim();
    }

    const { data } = await api.assistantChat(payload);
    const response = data as AssistantResponse;
    lastResponse.value = response;

    chatItems.value.push({
      role: "assistant",
      content: response.answer,
      createdAt: new Date().toISOString(),
    });

    if (response.risk_level === "BLOCKED") {
      ElMessage.warning("此問題被判定為高風險操作，已改為流程建議模式");
    }

    form.message = "";
    await scrollToBottom();
  } catch (error: any) {
    const messageText =
      error?.response?.data?.detail?.message ||
      error?.response?.data?.message ||
      error?.message ||
      "助理回覆失敗";

    chatItems.value.push({
      role: "assistant",
      content: `系統暫時無法回覆：${messageText}`,
      createdAt: new Date().toISOString(),
    });
    ElMessage.error(messageText);
    await scrollToBottom();
  } finally {
    loading.value = false;
  }
};

const runSuggestedAction = async (action: AssistantAction): Promise<void> => {
  if (!lastResponse.value) {
    return;
  }

  if (action.action_type === "navigate" && action.target && action.target.startsWith("/")) {
    await router.push(action.target);
    return;
  }

  if (action.action_type === "copy") {
    await navigator.clipboard.writeText(lastResponse.value.answer);
    ElMessage.success("已複製內容到剪貼簿");
    return;
  }

  if (action.action_type === "draft") {
    const draft = [
      "[Ask FinOps 待辦草稿]",
      `問題：${lastUserMessage.value || "(無)"}`,
      `主任務：${lastResponse.value.primary_task_id}`,
      `風險等級：${lastResponse.value.risk_level}`,
      `建議：${lastResponse.value.answer}`,
    ].join("\n");

    await navigator.clipboard.writeText(draft);
    ElMessage.success("待辦草稿已複製");
    return;
  }

  ElMessage.info("此動作目前僅作為資訊顯示");
};

const goToHistory = async (): Promise<void> => {
  await router.push("/assistant-history");
};
</script>

<style scoped>
.assistant-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.chat-card,
.meta-card {
  margin-bottom: 16px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  font-size: 18px;
  font-weight: 700;
  color: #173a63;
}

.hint {
  margin-top: 4px;
  font-size: 12px;
  color: #5a6f8b;
}

.chat-body {
  border: 1px solid #d9e5f4;
  border-radius: 12px;
  padding: 12px;
  min-height: 380px;
  max-height: 480px;
  overflow-y: auto;
  background: #f8fbff;
}

.chat-row {
  display: flex;
  margin-bottom: 10px;
}

.bubble {
  max-width: 90%;
  border-radius: 12px;
  padding: 10px 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.bubble-user {
  margin-left: auto;
  background: #dfeeff;
  border: 1px solid #bcd9f8;
}

.bubble-assistant {
  margin-right: auto;
  background: #ffffff;
  border: 1px solid #d9e5f4;
}

.meta {
  font-size: 12px;
  color: #62758f;
  margin-bottom: 4px;
}

.content {
  color: #1f2d3d;
}

.composer {
  margin-top: 12px;
}

.composer-actions {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.section {
  margin-top: 14px;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: #2a3f5f;
  margin-bottom: 8px;
}

.task-tag {
  margin-right: 6px;
  margin-bottom: 6px;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-item {
  border: 1px solid #d9e5f4;
  border-radius: 8px;
  padding: 8px;
  background: #f9fbff;
}

.source-key {
  font-size: 12px;
  color: #4e6583;
}

.source-label {
  font-size: 14px;
  color: #1f2d3d;
  font-weight: 600;
}

.source-meta {
  font-size: 12px;
  color: #62758f;
}

.action-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 900px) {
  .chat-body {
    min-height: 320px;
    max-height: 420px;
  }
}
</style>
