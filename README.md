# LLM API FinOps V1.1

此專案是公司內部 LLM API Key / AI 帳號 / Token 成本治理平台的 V1.1 嚴格實作。

## 文件入口
- 規劃書：[docs/LLM_API_FinOps_V1.1_Strict_Plan.md](docs/LLM_API_FinOps_V1.1_Strict_Plan.md)

## 技術棧
- Frontend：Vue 3 + Element Plus + ECharts
- Backend：FastAPI
- Database：PostgreSQL
- Cache：Redis
- Background Jobs：Celery/RQ 可替換；目前使用資料庫輪詢 worker
- Deployment：Docker Compose

## 建置來源說明
- Backend/Worker 的 Docker build 只使用 `backend/Dockerfile` 與 `backend/requirements.txt`。
- Frontend 的 Docker build 使用 `frontend/Dockerfile`。

## 快速啟動
1. 複製環境變數
   - `copy .env.example .env`
2. 產生主金鑰（32-byte URL-safe base64）填入 `MASTER_ENCRYPTION_KEY`
3. 啟動
   - `docker compose up --build`
4. 開啟
   - Backend: `http://localhost:18001/docs`
   - Frontend: `http://localhost:5173`

## 最小驗收測試（Smoke）
1. 先確認服務已啟動
   - `docker compose up -d --build`
2. 執行最小 Smoke 測試
   - `python -m unittest discover -s backend/tests -p "test_*.py" -v`

此測試會驗證 `healthz`、註冊選項、註冊與登入流程。

## 備份與還原（營運）
1. 建立 15 分鐘備份排程（Windows Task Scheduler）
   - `pwsh ./infra/backup/register_backup_task.ps1`
2. 立即執行單次備份
   - `pwsh ./infra/backup/backup_postgres.ps1`
3. 執行一鍵 restore drill（含 RPO/RTO 計算）
   - `pwsh ./infra/backup/run_restore_drill.ps1`
4. 檢視演練紀錄
   - `docs/Restore_Drill_Log.md`

備份/還原完整流程請見：`docs/Runbook_Backup_Restore.md`

## 預設帳號
- Email：`admin@example.com`
- Password：`ChangeThisPassword!`

首次啟動後請立即修改密碼。
