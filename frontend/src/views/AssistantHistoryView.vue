<!-- File Path: frontend/src/views/AssistantHistoryView.vue -->
<!-- Timestamp: 2026-05-26T13:00:00+08:00 -->
<!-- Version: v0.2 -->

<template>
  <el-row :gutter="12">
    <el-col :xs="24" :lg="10">
      <el-card>
        <template #header>
          <div class="header-row">
            <div>
              <div class="title">Assistant Conversations</div>
              <div class="hint">可追溯 Ask FinOps 對話 session 與風險狀態</div>
            </div>
            <el-button @click="loadConversations">重新整理</el-button>
          </div>
        </template>

        <div class="filters">
          <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" unlink-panels />
          <el-button @click="reloadConversations">查詢</el-button>
        </div>

        <el-table
          :data="conversations"
          v-loading="loadingConversations"
          height="560"
          highlight-current-row
          @current-change="onConversationChange"
        >
          <el-table-column prop="id" label="ID" width="90" />
          <el-table-column prop="session_id" label="Session ID" min-width="180" show-overflow-tooltip />
          <el-table-column prop="last_risk_level" label="Risk" width="110" />
          <el-table-column prop="last_message_at" label="Last Message" min-width="180" />
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
    </el-col>

    <el-col :xs="24" :lg="14">
      <el-card>
        <template #header>
          <div class="header-row">
            <div>
              <div class="title">Messages</div>
              <div class="hint" v-if="selectedConversationId">Conversation #{{ selectedConversationId }}</div>
              <div class="hint" v-else>請先在左側選擇 conversation</div>
            </div>
            <el-button :disabled="!selectedConversationId" @click="loadMessages">更新訊息</el-button>
          </div>
        </template>

        <el-empty v-if="!selectedConversationId" description="尚未選擇對話" :image-size="80" />

        <div v-else class="message-panel" v-loading="loadingMessages">
          <div v-for="item in messages" :key="item.id" class="message-item">
            <div class="meta">
              <el-tag size="small" :type="item.role === 'ASSISTANT' ? 'success' : 'info'">{{ item.role }}</el-tag>
              <el-tag size="small" :type="riskTagType(item.risk_level)">{{ item.risk_level || 'N/A' }}</el-tag>
              <span>ID {{ item.id }}</span>
              <span>{{ item.created_at }}</span>
            </div>
            <div class="content">{{ item.redacted_content }}</div>
            <div class="trace" v-if="item.trace_id">trace: {{ item.trace_id }}</div>
          </div>

          <el-empty v-if="messages.length === 0" description="此對話尚無訊息" :image-size="70" />
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

interface ConversationItem {
  id: number;
  session_id: string;
  last_risk_level: string | null;
  last_message_at: string;
}

interface MessageItem {
  id: number;
  role: string;
  risk_level: string | null;
  redacted_content: string;
  trace_id: string | null;
  created_at: string;
}

const conversations = ref<ConversationItem[]>([]);
const messages = ref<MessageItem[]>([]);
const loadingConversations = ref(false);
const loadingMessages = ref(false);
const selectedConversationId = ref<number | null>(null);
const dateRange = ref<[string, string] | null>(null);
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const extractErrorMessage = (error: any, fallback: string): string => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (typeof first === "string") {
      return first;
    }
    if (typeof first?.msg === "string") {
      return first.msg;
    }
  }
  if (typeof error?.response?.data?.message === "string" && error.response.data.message.trim()) {
    return error.response.data.message;
  }
  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message;
  }
  return fallback;
};

const riskTagType = (riskLevel: string | null): "success" | "warning" | "danger" | "info" => {
  if (riskLevel === "BLOCKED") {
    return "danger";
  }
  if (riskLevel === "HIGH") {
    return "warning";
  }
  if (riskLevel === "LOW") {
    return "success";
  }
  return "info";
};

const loadConversations = async (): Promise<void> => {
  loadingConversations.value = true;
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
      sort_by: "last_message_at",
      sort_order: "desc",
    };

    if (dateRange.value) {
      params.start_at = `${dateRange.value[0]}T00:00:00Z`;
      params.end_at = `${dateRange.value[1]}T23:59:59Z`;
    }

    const { data } = await api.assistantConversations(params);
    conversations.value = Array.isArray(data?.items) ? data.items : [];
    total.value = Number(data?.meta?.total || 0);

    if (conversations.value.length === 0) {
      selectedConversationId.value = null;
      messages.value = [];
      return;
    }

    if (!selectedConversationId.value || !conversations.value.some((item) => item.id === selectedConversationId.value)) {
      selectedConversationId.value = conversations.value[0].id;
      await loadMessages();
    }
  } catch (error: any) {
    ElMessage.error(extractErrorMessage(error, "載入 assistant conversations 失敗"));
  } finally {
    loadingConversations.value = false;
  }
};

const reloadConversations = async (): Promise<void> => {
  page.value = 1;
  await loadConversations();
};

const onPageChange = async (nextPage: number): Promise<void> => {
  page.value = nextPage;
  await loadConversations();
};

const onConversationChange = async (row: ConversationItem | null): Promise<void> => {
  if (!row) {
    return;
  }
  selectedConversationId.value = row.id;
  await loadMessages();
};

const loadMessages = async (): Promise<void> => {
  if (!selectedConversationId.value) {
    messages.value = [];
    return;
  }

  loadingMessages.value = true;
  try {
    const { data } = await api.assistantConversationMessages(selectedConversationId.value, {
      page: 1,
      page_size: 200,
      sort_by: "created_at",
      sort_order: "asc",
    });
    messages.value = Array.isArray(data?.items) ? data.items : [];
  } catch (error: any) {
    ElMessage.error(extractErrorMessage(error, "載入 conversation messages 失敗"));
  } finally {
    loadingMessages.value = false;
  }
};

onMounted(loadConversations);
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.title {
  font-size: 17px;
  font-weight: 700;
  color: #173a63;
}

.hint {
  margin-top: 4px;
  font-size: 12px;
  color: #607793;
}

.filters {
  margin-bottom: 10px;
  display: flex;
  gap: 8px;
}

.message-panel {
  min-height: 560px;
  max-height: 560px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.message-item {
  border: 1px solid #d9e5f4;
  background: #f8fbff;
  border-radius: 10px;
  padding: 10px;
}

.meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #5a708c;
}

.content {
  white-space: pre-wrap;
  line-height: 1.6;
  color: #21354f;
}

.trace {
  margin-top: 8px;
  font-size: 12px;
  color: #7b8ea7;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1200px) {
  .message-panel {
    min-height: 420px;
    max-height: 420px;
  }
}
</style>
