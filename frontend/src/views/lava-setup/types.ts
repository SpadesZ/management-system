export interface LavaModelOption {
  id: string;
  label: string;
}

export type LavaModelInput =
  | string
  | {
      id?: string;
      name?: string;
      is_free?: boolean;
    };

export interface LavaConnection {
  id: number;
  name: string;
  vendor: string;
  api_key: string;
  model_name: string;
  status: string;
  available_models?: LavaModelInput[];
}

export interface LavaBinding {
  task_id: string;
  task_name?: string;
  connection_id: number | null;
  is_locked: boolean;
}

export interface LavaPolicy {
  total_lines: number;
  nemotron_lines: number;
  max_nemotron: number;
  target_is_nemotron: boolean;
  allow_nemotron: boolean;
  projected_nemotron: number;
}

export interface SelectOption {
  value: string;
  label: string;
}

export interface CPUInfo {
  logical_cores: number;
  effective_cores: number;
}

export interface ConnectionEditor {
  id: number | null;
  name: string;
  vendor: string;
  api_key: string;
  model_name: string;
  status: string;
}
