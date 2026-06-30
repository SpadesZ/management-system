# Backup / Restore Runbook (V1.1)

## 1. 目標
- RPO: 15 分鐘
- RTO: 4 小時

## 2. 備份策略
- PostgreSQL 使用每日全量備份 + WAL 保留。
- 每日產生備份檔，保留至少 30 天。
- 備份檔案上傳到公司內部備份儲存並校驗 SHA256。

### 2.1 執行工具
- 單次備份：`pwsh ./infra/backup/backup_postgres.ps1`
- 建立排程：`pwsh ./infra/backup/register_backup_task.ps1`
- 預設排程名稱：`TokenButler-Postgres-Backup-15m`
- 備份輸出目錄：`infra/backups`

## 3. 還原步驟
1. 停止寫入流量（維護模式）。
2. 建立新 PostgreSQL 實例。
3. 還原最新全量備份。
4. 回放 WAL 到目標時間點。
5. 執行資料完整性檢查：
   - usage_events 筆數抽樣
   - cost_ledger 與 usage_events request_id 對照
   - 最近 1 小時 gateway_requests 狀態一致性
6. 重新啟動 backend / worker。
7. 解除維護模式。

## 4. 每月演練模板
- 演練日期
- 演練範圍
- 備份版本
- 還原耗時（分鐘）
- 成功/失敗
- 發現問題
- 修復措施
- 負責人

## 5. 實際演練流程（建議每月至少一次）
1. 執行 `pwsh ./infra/backup/run_restore_drill.ps1`。
2. 觀察輸出欄位：
   - `restore_minutes` 必須 <= 240
   - `rpo_minutes` 必須 <= 15
   - `status` 必須為 `PASS`
3. 將結果新增至 `docs/Restore_Drill_Log.md`。
4. 若失敗，記錄 root cause 與修復計畫，並在修復後重跑一次演練。
