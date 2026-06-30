<!-- File Path: frontend/src/views/DashboardView.vue -->
<!-- Timestamp: 2026-05-25T12:00:00+08:00 -->
<!-- Version: v0.1 -->

<template>
  <div class="dashboard">
    <div class="stats-grid">
      <el-card>
        <div class="stat-title">今日 Tokens</div>
        <div class="stat-value">{{ summary.today_tokens.toLocaleString() }}</div>
      </el-card>
      <el-card>
        <div class="stat-title">今日成本 (USD)</div>
        <div class="stat-value">{{ Number(summary.today_cost_usd).toFixed(6) }}</div>
      </el-card>
      <el-card>
        <div class="stat-title">本月 Tokens</div>
        <div class="stat-value">{{ summary.month_tokens.toLocaleString() }}</div>
      </el-card>
      <el-card>
        <div class="stat-title">本月成本 (USD)</div>
        <div class="stat-value">{{ Number(summary.month_cost_usd).toFixed(6) }}</div>
      </el-card>
    </div>

    <div class="chart-grid">
      <el-card>
        <template #header>用量趨勢概覽</template>
        <div ref="chartRef" class="chart" />
      </el-card>

      <el-card>
        <template #header>告警中心</template>
        <el-table :data="alerts" height="320">
          <el-table-column prop="severity" label="Severity" width="120" />
          <el-table-column prop="title" label="Title" min-width="180" />
          <el-table-column prop="status" label="Status" width="120" />
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import * as echarts from "echarts";

import { api } from "../api/endpoints";

interface SummaryState {
  today_tokens: number;
  today_cost_usd: number;
  month_tokens: number;
  month_cost_usd: number;
}

const chartRef = ref<HTMLDivElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

const summary = ref<SummaryState>({
  today_tokens: 0,
  today_cost_usd: 0,
  month_tokens: 0,
  month_cost_usd: 0,
});

const alerts = ref<Array<{ id: number; severity: string; title: string; status: string }>>([]);

const renderChart = (): void => {
  if (!chartRef.value) {
    return;
  }
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value);
  }
  chartInstance.setOption({
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    },
    yAxis: { type: "value" },
    series: [
      {
        type: "line",
        smooth: true,
        data: [120000, 160000, 150000, 190000, 180000, 220000, 200000],
        areaStyle: {},
      },
    ],
  });
};

const fetchData = async (): Promise<void> => {
  try {
    const [summaryResp, alertResp] = await Promise.all([api.dashboardSummary(), api.dashboardAlerts()]);
    summary.value = summaryResp.data;
    alerts.value = alertResp.data;
  } catch (error: any) {
    const message = error?.response?.data?.detail?.message || "載入 Dashboard 失敗";
    ElMessage.error(message);
  }
};

onMounted(async () => {
  await fetchData();
  renderChart();
  window.addEventListener("resize", renderChart);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", renderChart);
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
});
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-title {
  color: #607a9c;
  font-size: 14px;
}

.stat-value {
  margin-top: 6px;
  font-size: 24px;
  font-weight: 700;
  color: #1c3554;
}

.chart-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 12px;
}

.chart {
  height: 320px;
}

@media (max-width: 1000px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
