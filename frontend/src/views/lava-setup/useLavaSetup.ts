import { reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { api } from "../../api/endpoints";
import type {
  ConnectionEditor,
  CPUInfo,
  LavaBinding,
  LavaConnection,
  LavaModelInput,
  LavaModelOption,
  LavaPolicy,
  SelectOption,
} from "./types";

const extractErrorMessage = (error: unknown, fallback: string): string => {
  const err = error as {
    response?: {
      data?: {
        message?: string;
        detail?: {
          message?: string;
        };
      };
    };
    message?: string;
  };

  return err?.response?.data?.message || err?.response?.data?.detail?.message || err?.message || fallback;
};

const normalizeModelOptions = (models: LavaModelInput[] | undefined): LavaModelOption[] => {
  if (!models || models.length === 0) {
    return [];
  }

  const seen = new Set<string>();
  const normalized: LavaModelOption[] = [];

  for (const model of models) {
    if (typeof model === "string") {
      const id = model.trim();
      if (!id || seen.has(id)) {
        continue;
      }
      seen.add(id);
      normalized.push({ id, label: id });
      continue;
    }

    const id = String(model.id || "").trim();
    if (!id || seen.has(id)) {
      continue;
    }
    seen.add(id);

    const name = String(model.name || id).trim();
    const label = model.is_free ? `${name} (free)` : name;
    normalized.push({ id, label });
  }

  return normalized;
};

export const useLavaSetup = () => {
  const connections = ref<LavaConnection[]>([]);
  const bindings = ref<LavaBinding[]>([]);
  const modelOptions = ref<LavaModelOption[]>([]);
  const lastPolicy = ref<LavaPolicy | null>(null);

  const connectionEditor = reactive<ConnectionEditor>({
    id: null,
    name: "",
    vendor: "openrouter",
    api_key: "",
    model_name: "",
    status: "draft",
  });

  const selectedConnectionId = ref<number | null>(null);

  const loadingConnections = ref(false);
  const loadingBindings = ref(false);
  const creatingConnection = ref(false);
  const savingConnection = ref(false);
  const deletingConnection = ref(false);
  const fetchingModels = ref(false);
  const testingConnection = ref(false);

  const loadingRuntimeCPU = ref(false);
  const savingRuntimeCPU = ref(false);
  const loadingRuntimeWorkers = ref(false);
  const savingRuntimeWorkers = ref(false);

  const cpuChoices = ref<SelectOption[]>([]);
  const cpuSelected = ref("auto");
  const cpuLimit = ref<CPUInfo>({ logical_cores: 1, effective_cores: 1 });

  const workerChoices = ref<SelectOption[]>([]);
  const workerSelected = ref("1");
  const effectiveWorkers = ref(1);

  const resetEditor = (): void => {
    selectedConnectionId.value = null;
    connectionEditor.id = null;
    connectionEditor.name = "";
    connectionEditor.vendor = "openrouter";
    connectionEditor.api_key = "";
    connectionEditor.model_name = "";
    connectionEditor.status = "draft";
    modelOptions.value = [];
    lastPolicy.value = null;
  };

  const setEditorFromConnection = (row: LavaConnection): void => {
    selectedConnectionId.value = row.id;
    connectionEditor.id = row.id;
    connectionEditor.name = row.name || "";
    connectionEditor.vendor = row.vendor || "openrouter";
    connectionEditor.api_key = "";
    connectionEditor.model_name = row.model_name || "";
    connectionEditor.status = row.status || "draft";
    modelOptions.value = normalizeModelOptions(row.available_models);
  };

  const selectConnection = (row: LavaConnection): void => {
    setEditorFromConnection(row);
  };

  const loadConnections = async (preferredConnectionId?: number): Promise<void> => {
    loadingConnections.value = true;
    try {
      const { data } = await api.lavaConnections();
      const rows = (data.connections || []) as LavaConnection[];
      connections.value = rows;

      const targetId = preferredConnectionId ?? selectedConnectionId.value;
      const selected = rows.find((item) => item.id === targetId) || rows.find((item) => item.id === connectionEditor.id) || rows[0];

      if (selected) {
        setEditorFromConnection(selected);
      } else {
        resetEditor();
      }
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "載入 LAVA connections 失敗"));
    } finally {
      loadingConnections.value = false;
    }
  };

  const loadBindings = async (): Promise<void> => {
    loadingBindings.value = true;
    try {
      const { data } = await api.lavaBindings();
      bindings.value = (data.bindings || []) as LavaBinding[];
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "載入 task bindings 失敗"));
    } finally {
      loadingBindings.value = false;
    }
  };

  const loadRuntimeCPU = async (): Promise<void> => {
    loadingRuntimeCPU.value = true;
    try {
      const { data } = await api.lavaRuntimeCPU();
      cpuChoices.value = (data.choices || []) as SelectOption[];
      cpuSelected.value = String(data.selected_value || "auto");
      cpuLimit.value = {
        logical_cores: Number(data.cpu_limit?.logical_cores || 1),
        effective_cores: Number(data.cpu_limit?.effective_cores || 1),
      };
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "載入 CPU runtime 設定失敗"));
    } finally {
      loadingRuntimeCPU.value = false;
    }
  };

  const loadRuntimeWorkers = async (): Promise<void> => {
    loadingRuntimeWorkers.value = true;
    try {
      const { data } = await api.lavaRuntimeFlowaWorkers();
      workerChoices.value = (data.choices || []) as SelectOption[];
      workerSelected.value = String(data.selected_value || "1");
      effectiveWorkers.value = Number(data.effective_workers || 1);
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "載入 workers runtime 設定失敗"));
    } finally {
      loadingRuntimeWorkers.value = false;
    }
  };

  const loadAll = async (): Promise<void> => {
    await Promise.all([loadConnections(), loadBindings(), loadRuntimeCPU(), loadRuntimeWorkers()]);
  };

  const createConnection = async (): Promise<void> => {
    creatingConnection.value = true;
    try {
      const { data } = await api.lavaCreateConnection();
      const newId = Number(data.connection?.id || 0) || undefined;
      await loadConnections(newId);
      await loadBindings();
      ElMessage.success("已新增 LAVA 線路");
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "新增線路失敗"));
    } finally {
      creatingConnection.value = false;
    }
  };

  const saveConnection = async (): Promise<void> => {
    if (!connectionEditor.id) {
      ElMessage.warning("請先選擇一條線路");
      return;
    }

    savingConnection.value = true;
    try {
      const payload: Record<string, unknown> = {
        id: connectionEditor.id,
        name: connectionEditor.name,
        vendor: connectionEditor.vendor,
        model_name: connectionEditor.model_name,
        status: connectionEditor.status,
        available_models: modelOptions.value.map((model) => model.id),
      };

      if (connectionEditor.api_key.trim()) {
        payload.api_key = connectionEditor.api_key.trim();
      }

      await api.lavaUpdateConnection(payload);
      connectionEditor.api_key = "";
      await loadConnections(connectionEditor.id);
      ElMessage.success("線路設定已儲存");
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "儲存線路失敗"));
    } finally {
      savingConnection.value = false;
    }
  };

  const fetchModels = async (): Promise<void> => {
    if (!connectionEditor.id) {
      ElMessage.warning("請先選擇一條線路");
      return;
    }

    fetchingModels.value = true;
    try {
      const payload: Record<string, unknown> = {
        vendor: connectionEditor.vendor,
        conn_id: connectionEditor.id,
      };

      if (connectionEditor.api_key.trim()) {
        payload.api_key = connectionEditor.api_key.trim();
      }

      const { data } = await api.lavaFetchModels(payload);
      modelOptions.value = normalizeModelOptions((data.models || []) as LavaModelInput[]);
      lastPolicy.value = (data.policy || null) as LavaPolicy | null;

      if (!connectionEditor.model_name && modelOptions.value.length > 0) {
        connectionEditor.model_name = modelOptions.value[0].id;
      }

      ElMessage.success(`已取得 ${modelOptions.value.length} 個模型`);
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "模型抓取失敗"));
    } finally {
      fetchingModels.value = false;
    }
  };

  const testConnection = async (): Promise<void> => {
    if (!connectionEditor.id) {
      ElMessage.warning("請先選擇一條線路");
      return;
    }

    testingConnection.value = true;
    try {
      const payload: Record<string, unknown> = {
        conn_id: connectionEditor.id,
        vendor: connectionEditor.vendor,
        model_name: connectionEditor.model_name,
      };

      if (connectionEditor.api_key.trim()) {
        payload.api_key = connectionEditor.api_key.trim();
      }

      const { data } = await api.lavaTestConnection(payload);
      ElMessage.success(String(data.message || "線路測試成功"));
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "線路測試失敗"));
    } finally {
      testingConnection.value = false;
    }
  };

  const deleteCurrentConnection = async (): Promise<void> => {
    if (!connectionEditor.id) {
      ElMessage.warning("請先選擇一條線路");
      return;
    }

    try {
      await ElMessageBox.confirm(`確定刪除線路 #${connectionEditor.id} 嗎？`, "刪除確認", {
        type: "warning",
        confirmButtonText: "刪除",
        cancelButtonText: "取消",
      });
    } catch {
      return;
    }

    deletingConnection.value = true;
    try {
      await api.lavaDeleteConnection(connectionEditor.id);
      await loadConnections();
      await loadBindings();
      ElMessage.success("線路已刪除");
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "刪除線路失敗"));
    } finally {
      deletingConnection.value = false;
    }
  };

  const onBindingConnectionChange = async (row: LavaBinding): Promise<void> => {
    if (row.is_locked) {
      ElMessage.warning("此 task binding 已鎖定");
      return;
    }

    try {
      await api.lavaUpdateBinding({
        task_id: row.task_id,
        connection_id: row.connection_id ?? null,
      });
      ElMessage.success(`${row.task_id} 綁定已更新`);
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "更新 task binding 失敗"));
      await loadBindings();
    }
  };

  const toggleBindingLock = async (row: LavaBinding): Promise<void> => {
    try {
      if (row.is_locked) {
        await api.lavaUnlockBinding({ task_id: row.task_id });
        ElMessage.success(`${row.task_id} 已解鎖`);
      } else {
        await api.lavaLockBinding({ task_id: row.task_id });
        ElMessage.success(`${row.task_id} 已鎖定`);
      }
      await loadBindings();
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "切換 lock 狀態失敗"));
    }
  };

  const testBinding = async (row: LavaBinding): Promise<void> => {
    try {
      const { data } = await api.lavaTestBinding({ task_id: row.task_id });
      ElMessage.success(String(data.message || "Binding 測試成功"));
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "Binding 測試失敗"));
    }
  };

  const saveRuntimeCPU = async (): Promise<void> => {
    savingRuntimeCPU.value = true;
    try {
      await api.lavaUpdateRuntimeCPU({ cpu_cores: cpuSelected.value });
      await loadRuntimeCPU();
      ElMessage.success("CPU 設定已更新");
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "CPU 設定更新失敗"));
    } finally {
      savingRuntimeCPU.value = false;
    }
  };

  const saveRuntimeWorkers = async (): Promise<void> => {
    savingRuntimeWorkers.value = true;
    try {
      await api.lavaUpdateRuntimeFlowaWorkers({ page_workers: workerSelected.value });
      await loadRuntimeWorkers();
      ElMessage.success("Workers 設定已更新");
    } catch (error: unknown) {
      ElMessage.error(extractErrorMessage(error, "Workers 設定更新失敗"));
    } finally {
      savingRuntimeWorkers.value = false;
    }
  };

  return {
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
  };
};
