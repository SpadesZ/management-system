# GoLive Acceptance Checklist

> 歷史驗收紀錄：保留原勾選項目。2026-10-02 presentation review 未重新確認目前 production 部署、外部計費或完整 Go-Live 驗收；請勿將本表當成目前環境的健康報告。

## P0 先決條件（部署與最小可驗證）
- [x] backend build context 內有可用 Dockerfile（backend/Dockerfile）
- [x] backend build context 內有可用 requirements（backend/requirements.txt）
- [x] docker-compose 明確指定 backend/worker/frontend dockerfile
- [x] 最小 smoke tests 已存在並可執行（healthz、register options、register+login）
- [x] README 已提供 smoke tests 執行指令

## P1 權限與治理（已完成）
- [x] RBAC deny-by-default 與 role_permissions 真正落地
- [x] Gateway entitlement 檢查與政策拒絕碼/訊息
- [x] API key 生命週期（建立/輪替/停用）政策覆核

## P2 一致性與金流完整性（已完成）
- [x] usage_events request_id 冪等唯一約束
- [x] ledger 寫入冪等鍵與重放保護
- [x] reservation/commit/release 競態保護

## P3 可觀測性與營運（已完成）
- [x] 計費準確度監控與對帳報表
- [x] 錯誤預算與告警分級
- [x] worker 任務積壓與死信檢查

## P4 測試與交付（已完成）
- [x] API 合約測試（成功/失敗/邊界）
- [x] 權限矩陣自動化測試
- [x] 匯出/稽核路徑壓力測試
