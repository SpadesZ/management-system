<!-- File Path: frontend/src/views/ROIAnalyticsView.vue -->
<!-- Timestamp: 2026-05-26T13:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <div class="roi-grid">
    <el-card class="summary-card">
      <template #header>
        <div class="header-row">
          <div>
            <div class="title">ROI Analytics</div>
            <div class="hint">官方 ROI 僅計算 APPROVED work outputs</div>
          </div>
          <div class="actions">
            <el-select v-model="groupBy" style="width: 160px" @change="reload">
              <el-option label="Department" value="department" />
              <el-option label="User" value="user" />
              <el-option label="Project" value="project" />
              <el-option label="Asset" value="asset" />
            </el-select>
            <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" unlink-panels />
            <el-button :loading="loading" @click="reload">查詢</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="12" class="stat-grid">
        <el-col :xs="24" :sm="8">
          <div class="stat-box">
            <div class="label">Total Cost USD</div>
            <div class="value">{{ totals.cost_usd }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="stat-box">
            <div class="label">Total Value USD</div>
            <div class="value">{{ totals.value_usd }}</div>
          </div>
        </el-col>
        <el-col :xs="24" :sm="8">
          <div class="stat-box">
            <div class="label">ROI Ratio</div>
            <div class="value">{{ totals.roi_ratio || "N/A" }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card>
      <template #header>
        <div class="sub-title">群組明細（{{ groupBy }}）</div>
      </template>

      <el-table :data="rows" v-loading="loading" stripe height="540">
        <el-table-column prop="group_key" label="Group Key" min-width="220" />
        <el-table-column prop="output_count" label="Outputs" width="120" />
        <el-table-column prop="cost_usd" label="Cost USD" width="150" />
        <el-table-column prop="value_usd" label="Value USD" width="150" />
        <el-table-column prop="roi_ratio" label="ROI Ratio" width="140" />
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { api } from "../api/endpoints";

interface ROINode {
  group_key: string;
  output_count: number;
  cost_usd: string;
  value_usd: string;
  roi_ratio: string | null;
}

interface ROITotals {
  cost_usd: string;
  value_usd: string;
  output_count: number;
  roi_ratio: string | null;
}

const loading = ref(false);
const groupBy = ref<"department" | "user" | "project" | "asset">("department");
const dateRange = ref<[string, string] | null>(null);
const rows = ref<ROINode[]>([]);
const totals = ref<ROITotals>({
  cost_usd: "0.000000",
  value_usd: "0.000000",
  output_count: 0,
  roi_ratio: null,
});

const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const load = async (): Promise<void> => {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
      group_by: groupBy.value,
      sort_by: "id",
      sort_order: "desc",
    };

    if (dateRange.value) {
      params.start_at = `${dateRange.value[0]}T00:00:00Z`;
      params.end_at = `${dateRange.value[1]}T23:59:59Z`;
    }

    const { data } = await api.analyticsRoi(params);
    rows.value = Array.isArray(data?.items) ? data.items : [];
    totals.value = (data?.totals || totals.value) as ROITotals;
    total.value = Number(data?.meta?.total || 0);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "載入 ROI 分析失敗");
  } finally {
    loading.value = false;
  }
};

const reload = async (): Promise<void> => {
  page.value = 1;
  await load();
};

const onPageChange = async (nextPage: number): Promise<void> => {
  page.value = nextPage;
  await load();
};

onMounted(load);
</script>

<style scoped>
.roi-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

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
  font-size: 12px;
  color: #607793;
}

.sub-title {
  font-size: 14px;
  font-weight: 700;
  color: #173a63;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.stat-grid {
  margin-top: 4px;
}

.stat-box {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid #d8e4f5;
  background: linear-gradient(160deg, #f8fbff 0%, #eef5ff 100%);
}

.label {
  font-size: 12px;
  color: #5f7794;
}

.value {
  margin-top: 6px;
  font-size: 20px;
  font-weight: 700;
  color: #14365e;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 1000px) {
  .header-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .actions {
    justify-content: flex-start;
  }
}
</style>
