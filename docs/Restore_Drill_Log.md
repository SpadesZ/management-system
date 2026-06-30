# Restore Drill Log

| 日期 (UTC) | 備份檔 | 還原資料庫 | 還原耗時(分鐘) | RPO(分鐘) | 目標RTO<=240 | 目標RPO<=15 | 結果 | 備註 |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- |
| 2026-05-30T09:43:44Z | llm_finops_20260530_094344.dump | llm_finops_restore_drill | 0.091 | 0.092 | PASS | PASS | PASS | SUCCESS_USAGE_EVENTS=46, COST_LEDGER=46, MISSING_LEDGER_PAIRS_FOR_SUCCESS=0 |
| 2026-05-30T09:45:17Z | llm_finops_20260530_094517.dump | llm_finops_restore_drill | 0.092 | 0.096 | PASS | PASS | PASS | SUCCESS_USAGE_EVENTS=46, COST_LEDGER=46, MISSING_LEDGER_PAIRS_FOR_SUCCESS=0 |
