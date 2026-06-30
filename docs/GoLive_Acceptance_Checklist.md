# V1.1 上線驗收清單

## 權限與資料域
- [x] Deny by default 已生效。
- [x] Role 與 scope filter 已覆蓋所有列表 API。
- [x] Manager 無法查詢非轄下部門資料。
- [x] Finance 無法解密 API key。

## API Key 安全
- [x] API key 以信封加密寫入。
- [x] API 回應僅回 masked_key。
- [x] 稽核日志有 key create/rotate/disable 記錄。
- [x] 匯出檔不含完整 key。

## 成本正確性
- [x] usage_events 與 cost_ledger 成對寫入。
- [x] request_id 重試不重複寫 ledger。
- [x] price_version_id 寫入 usage_events 與 cost_ledger。
- [x] model_prices 不允許重疊區間。

## Gateway 穩定性
- [x] connect timeout / provider timeout 生效。
- [x] retry 只在可重試錯誤觸發。
- [x] timeout 情境進入 UNKNOWN_PROVIDER_STATE / PENDING_RECONCILIATION。
- [x] budget reservation 在失敗/成功都能進正確狀態。

## 分區與報表
- [x] usage_events 按月分區建立。
- [x] summary 查詢不掃原始 usage_events 全表。
- [x] export_jobs 背景匯出可運作。

## 備份與還原
- [x] 每日備份排程存在。
- [x] 還原演練至少每月一次並有紀錄。
- [x] RPO 15 分鐘、RTO 4 小時驗證通過。

## 驗證證據
- backend 全量 live tests：`python -m unittest discover -v tests`（19 tests, OK）
- 備份排程：`TokenButler-Postgres-Backup-15m`（每 15 分鐘）
- 還原演練：`docs/Restore_Drill_Log.md` 最新紀錄 PASS
