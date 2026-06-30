# LLM API Key / AI 帳號 / Token 成本管理系統 V1.1 嚴格規劃書

版本：v1.1.0  
日期：2026-05-25  
適用範圍：公司內部 LLM 資產、權限、成本治理與 Gateway 平台

## 1. 系統定位與設計原則

本系統是公司內部使用的 LLM 資產管理、AI 使用權限控管、Token 成本治理、API Gateway 與 AI FinOps 平台。

核心目標：
- 管理公司所有 LLM API key、AI 付費帳號與 license。
- 統一控管員工、部門、專案可用模型與額度。
- 所有 LLM 請求必須經過公司 Gateway。
- 每次請求都記錄 token、成本、權限、狀態與稽核資訊。
- 成本可追溯、權限可驗證、API key 不外洩、報表可對帳。

一句話原則：
- LLM 可以輔助分析，但不能決定權限、預算、解密、停用或刪除。

不可妥協原則：
- Deny by default。
- 最嚴格限制優先。
- 所有敏感操作必須稽核可追蹤。
- 成本帳務與即時估算分離。
- 不得因重試導致重複扣費。

## 2. 技術架構與非功能需求

技術選型：
- Frontend：Vue 3 + Element Plus + ECharts
- Backend：FastAPI
- Database：PostgreSQL
- Cache / Rate Limit：Redis
- Background Jobs：Celery（預設）或 RQ
- LLM Access Layer：Internal LLM Gateway
- Deployment：Docker Compose 起步，後續可升 Kubernetes

資料分層：
- PostgreSQL：主資料、權限、帳務 ledger、usage events、summary
- Redis：rate limit、budget reservation、短期狀態
- 事件外部倉儲預留：ClickHouse / BigQuery（V1.1 不導入）

可用性與效能目標（SLO）：
- Gateway 月可用性：99.9%
- Gateway p95 latency（不含 provider）：< 300ms
- Gateway p95 end-to-end（含 provider）：< 8s（常態）
- Dashboard 查詢（summary）：p95 < 2s
- 單日 30 萬 usage events 可持續寫入
- 峰值寫入能力目標：50 req/s 可平穩運作

## 3. 核心流程（含防重複扣費）

流程：
1. Client 送出請求到 Backend / Gateway。
2. 建立 gateway_requests（狀態：PENDING）。
3. 身份驗證、資料域檢查、權限檢查。
4. 計算 effective budget（soft/hard）與預估成本。
5. 建立 budget_reservation（RESERVED）。
6. 執行 rate limit。
7. 選擇可用 API key（狀態可用、未過期、符合 entitlements）。
8. 呼叫 provider（含 timeout / retry / circuit breaker）。
9. 取得回覆後，寫 usage_events（append-only）。
10. 寫 cost_ledger（不可覆寫）。
11. settle reservation（保留轉已使用，並釋放剩餘額度）。
12. 更新 gateway_requests（SUCCESS / FAILED / UNKNOWN）。
13. 觸發 summary、alerts、觀測指標。
14. 回傳 AI 回覆與 estimated_cost_usd。

冪等規則：
- request_id 全域唯一。
- idempotency_key + requester 維度唯一。
- 同一 request_id 或同一 idempotency_key 重試不得重複寫 ledger。

## 4. 功能範圍

V1.1 必做：
- 使用者、部門、角色、資料域管理。
- API key 資產管理（加密、遮罩、輪替、停用）。
- AI 付費帳號與 license 管理。
- 模型與模型價格版本管理。
- 使用者 / 部門 / 專案 / API key 額度管理。
- 申請與多層審核流程。
- LLM Gateway 統一轉發與記錄。
- usage_events 原始事件表（分區）。
- cost_ledger 成本流水表（不可變）。
- 成本 Dashboard、daily summary。
- 告警中心。
- CSV / Excel 背景匯出。
- Audit log。
- Gateway timeout、retry、circuit breaker。
- 備份與還原策略。

V1.1 不做：
- 自動 ROI 深度分析。
- 完整 AI 模型推薦。
- 多 provider 自動 fallback。
- ClickHouse / BigQuery 正式導入。
- 全面 Policy-as-Code。
- 讓 LLM 自動執行高風險操作。

## 5. 角色、資料域與統一 Scope Filter

角色：
- Admin：全域設定與資產管理。
- Finance：全域成本與對帳可見，不可解密 key。
- Manager：自己部門與子部門可見，可審核部門申請。
- Employee：僅本人資料可見。
- Auditor：唯讀稽核資料。
- Security：安全事件與 key 風險可見。

資料域規則：
- 所有查詢必須經過統一 scope filter。
- 禁止在各 API 各自拼接權限條件。
- scope filter 支援 user / department / descendant departments。

## 6. 權限與額度衝突規則

固定規則：
- deny by default
- 最嚴格限制優先
- 所有適用層級都必須通過

適用層級：
- User
- Department
- Project
- API Key
- Provider
- Model

預算型別：
- soft limit：超過後告警，不阻擋。
- hard limit：超過後立即阻擋。

有效額度：
- effective_soft_limit = min(所有適用 soft limit)
- effective_hard_limit = min(所有適用 hard limit)

## 7. 成本與帳務規則（精度、幣別、對帳）

雙軌成本：
- 即時估算：回應 estimated_cost_usd。
- 正式帳務：cost_ledger 為唯一結算依據。

精度規則：
- 所有貨幣欄位使用 NUMERIC(18,6)。
- 所有 token 相關成本計算使用 decimal，不使用 float。
- API 回傳可顯示至小數第 6 位。

幣別規則：
- 系統標準幣別為 USD。
- 若 provider 原始帳單非 USD，需記錄原幣與匯率來源。
- 匯率表需保留版本與生效時間，對帳時不可回寫歷史紀錄。

對帳規則：
- provider 帳單匯入後，若與 ledger 差異超過閾值，建立 reconciliation issue。
- 不覆寫原 ledger，使用 adjustment ledger 補正。

## 8. 資料模型（V1.1）

主資料：
- users
- departments
- roles
- permissions
- providers
- models
- model_prices
- api_keys
- api_key_entitlements
- ai_accounts
- ai_account_assignments
- projects
- project_budgets
- approval_requests
- approval_steps

事件與成本：
- usage_events
- cost_ledger
- usage_daily_summary
- billing_imports
- billing_reconciliation_issues

營運與治理：
- audit_logs
- alert_rules
- alerts
- aggregation_jobs
- export_jobs
- budget_reservations
- gateway_requests

## 9. model_prices 版本一致性規則

必須保證：
- 同一 model_id 任一時點只允許一筆有效價格。
- effective_from / effective_to 不可重疊。
- usage_events 與 cost_ledger 必須寫入 price_version_id。

資料庫約束建議：
- UNIQUE(model_id, effective_from)
- CHECK(effective_to IS NULL OR effective_to > effective_from)
- 寫入前以交易鎖檢查區間重疊。

## 10. usage_events 分區與資料保留

分區策略：
- usage_events 採 created_at 月分區。
- 每月自動建立未來 3 個月分區。
- 自動檢查分區健康度，失敗需告警。

保留政策：
- usage_events 保存 12 個月。
- usage_daily_summary 保存 36 個月。

查詢策略：
- 查 usage_events 必須帶 time range。
- Dashboard 只能查 summary，不可掃全量 events。

彙總任務要求：
- 可重跑
- 可冪等
- 可追蹤 job status
- 不可重複累加

## 11. Idempotency 與重試規則

必要欄位：
- request_id
- idempotency_key

規則：
- request_id 全域唯一。
- usage_events.request_id unique。
- cost_ledger.request_id unique。
- provider timeout 後不得盲重送。
- 重試前先查 gateway_requests 先前狀態。

gateway_requests 狀態機：
- PENDING：已受理，尚未呼叫 provider。
- IN_FLIGHT：呼叫中。
- SUCCESS：已寫 usage + ledger。
- FAILED_RETRYABLE：可重試失敗。
- FAILED_FINAL：不可重試失敗。
- UNKNOWN_PROVIDER_STATE：timeout 或網路中斷，不確定 provider 是否成功。
- RECONCILING：待背景對帳確認。

## 12. Budget Reservation 狀態機

流程：
1. 預估成本。
2. 建立 reservation（RESERVED）。
3. 呼叫 provider。
4. 成功後 reservation -> SETTLED。
5. 失敗時 reservation -> RELEASED。
6. UNKNOWN_PROVIDER_STATE -> PENDING_RECONCILIATION。
7. 對帳後補正為 SETTLED 或 RELEASED。

一致性要求：
- 同一 request_id 只能對應一筆最終 settlement。
- 保證 reservation + ledger 狀態可追溯。

## 13. API Key 安全規範

加密：
- 採信封加密。
- DEK 加密 API key。
- KMS/master key 加密 DEK。
- 保存 kms_key_id、key_version。

顯示與存取限制：
- 前端不可取得完整 key。
- 一般 API 不回傳完整 key。
- log、匯出不得出現完整 key。
- 管理者預設只能看 masked key。

高風險操作（需二次確認或雙人覆核）：
- 解密 key
- 停用主要 key
- 修改全公司 hard limit
- 開放高價模型
- 大量匯出成本資料

## 14. Gateway 穩定性與錯誤規範

預設：
- connect timeout: 5s
- provider timeout: 60s
- retry: 最多 1 次

retryable：
- 429, 500, 502, 503, 504, network error

non-retryable：
- 400, 401, 403, hard limit exceeded

必備能力：
- rate limit
- circuit breaker
- request timeout
- provider error mapping
- standard error response
- request tracing

標準錯誤格式：
- request_id
- error_code
- message
- retryable

## 15. LLM 使用邊界治理

LLM 可用於：
- 申請內容摘要與分類
- 成本異常摘要
- 月報文字草稿
- token 節省建議
- 政策問答

LLM 禁止用於：
- 核准權限
- 調整預算
- 解密 API key
- 停用 API key
- 刪除資料
- 繞過審核
- 高風險直接執行

固定流程：
- LLM 建議 -> 人工審核 -> 系統規則執行 -> audit log

## 16. 告警規則與告警風暴控制

初版規則：
- 與近 7 日同時段平均比較超過 N 倍告警（預設 N=3）。
- 設最低流量門檻避免誤報。

告警類型：
- 成本暴增
- token 暴增
- API key 到期
- API key 未輪替
- 部門 soft limit 接近
- 部門 hard limit 命中
- provider error rate 過高
- worker lag 過高

治理：
- 相同來源與類型在冷卻時間內合併。
- 告警抑制窗口（maintenance window）。
- 重複告警去重 key。

## 17. 可觀測性與稽核

每個請求必帶：
- request_id
- trace_id
- user_id
- department_id
- project_id
- provider_id
- model_id

核心指標：
- Gateway p95 latency
- provider error rate
- timeout rate
- retry count
- budget reject count
- rate limit reject count
- cost drift
- worker lag
- DB query latency
- partition creation status

audit_logs 最低要求：
- actor_user_id
- action
- resource_type/resource_id
- source
- before_json/after_json
- ip_address
- created_at

## 18. 匯出治理

匯出策略：
- 所有 CSV / Excel 匯出必走 export_jobs。
- 大查詢不可同步阻塞 API。
- 匯出檔需 expires_at。
- 下載行為寫入 audit log。
- 依角色控制可匯出欄位與遮罩策略。

## 19. API 規格基準

主要 API：
- POST /auth/login
- GET /me
- GET /dashboard/summary
- GET /dashboard/alerts
- GET/POST/PATCH /users
- GET/POST/PATCH /departments
- GET/POST/PATCH /projects
- GET/POST/PATCH /api-keys
- POST /api-keys/{id}/rotate
- POST /api-keys/{id}/disable
- GET/POST/PATCH /models
- GET /usage-events
- GET /costs/summary
- GET /costs/by-user
- GET /costs/by-department
- GET /costs/by-model
- GET/POST /approval-requests
- POST /approval-requests/{id}/approve
- POST /approval-requests/{id}/reject
- POST /exports
- POST /gateway/chat

所有列表 API 必須支援：
- pagination
- sorting
- time range filter
- timezone
- scope filter

## 20. 測試與驗收矩陣

必測：
- 無權限不可呼叫模型。
- Manager 不能查其他部門資料。
- Finance 不能解密 API key。
- 敏感操作必有 audit log。
- hard limit 阻擋，soft limit 告警。
- request_id 重試不重複計費。
- ledger 能追 price_version_id。
- model_prices 區間不可重疊。
- usage_events 進正確月分區。
- Dashboard 走 summary。
- 匯出走 export_jobs。
- provider timeout 不拖垮 Gateway。
- key 不出現在 log/response/export。

## 21. 備份與災難復原

最低要求：
- PostgreSQL 每日備份。
- 支援 PITR。
- 每月 restore drill。
- 定義 RPO/RTO。

V1.1 目標：
- RPO：15 分鐘
- RTO：4 小時

演練驗收：
- 有完整還原步驟。
- 有演練報告（起訖時間、資料完整性、異常與改善）。
- 演練失敗必須追蹤修復。

## 22. 里程碑與工期

建議工期：8-10 週。

階段：
- W1-W2：基礎架構、DB schema、登入、RBAC、scope filter。
- W3-W4：API key、模型價格、AI 帳號、申請流程、audit log。
- W5-W6：Gateway、idempotency、budget reservation、events、ledger。
- W7-W8：Dashboard、summary、alerts、export_jobs、分區自動化。
- W9-W10：壓測、資安檢查、對帳測試、restore drill、UAT。

## 23. 上線門檻（Go-Live Gate）

全部成立才可上線：
- 權限衝突規則已實作。
- 資料域隔離測試矩陣通過。
- API key 明文不外洩。
- 重試不重複計費。
- ledger 可對帳。
- 分區與保留策略可運作。
- Dashboard 不掃原始大表。
- 匯出有治理與 audit。
- 高風險操作具雙重防護。
- provider timeout 不拖垮服務。
- 備份可成功還原。

## 24. V1.1 實作落地策略（本專案採用）

本專案會以以下目標落地：
- 先交付可執行的嚴謹骨架與核心流程。
- 先釘死資料正確性與安全性，再擴頁面細節。
- 所有關鍵邏輯提供可測試接口與可觀測欄位。
- 保留未來擴充到 ClickHouse / Kubernetes 的演進路徑。

以上規格是開發、測試、上線三方共同契約。
