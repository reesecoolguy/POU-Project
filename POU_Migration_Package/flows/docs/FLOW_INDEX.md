# Flow index

| Flow | Trigger | When it runs | Actions | Purpose |
|---|---|---|---:|---|
| [POU-Session](POU-Session.md) | Instant (Power Apps V2) | On demand from the app | 67 | Instant flow. LOGIN validates the badge and station and creates a session bound to the calling Microsoft accou |
| [POU-ProcessRequest](POU-ProcessRequest.md) | Instant (Power Apps V2) | On demand from the app / supervisor console | 218 | Instant flow called by the app with a RequestID. Claims the request, validates session/identity/permissions on |
| [POU-Sweeper](POU-Sweeper.md) | Recurrence 5 min | Every 5 minutes (probe costs ~6 actions when idle) | 239 | Scheduled every 5 minutes: processes Pending / stale-Processing requests with the same core, expires unanswere |
| [POU-Monitor](POU-Monitor.md) | Recurrence 1 h | Hourly | 37 | Hourly: raises ONE ops event (and one email) per failed or stuck request / ledger intent. |
| [POU-DailyLowStock](POU-DailyLowStock.md) | Recurrence 1 h (tick) | Once per local day at LowStockReportHourLocal | 54 | Hourly tick; sends once per day at the configured local hour. Replenishment SUGGESTIONS only. |
| [POU-Reconcile](POU-Reconcile.md) | Recurrence 1 h (tick) | Once per night at ReconcileHourLocal | 57 | Hourly tick; once per night: proves OnHandQty == the ledger row for StockVersion, repairs LowStockFlag, raises |
| [POU-WeeklyHealth](POU-WeeklyHealth.md) | Recurrence 1 h (tick) | Weekly on WeeklyDayOfWeek / WeeklyHourLocal | 85 | Hourly tick; once per week: orphans, parameters, roles, placeholders; repairs the denormalised ItemName. |
| [POU-WeeklyUsage](POU-WeeklyUsage.md) | Recurrence 1 h (tick) | Weekly on WeeklyDayOfWeek / WeeklyHourLocal | 44 | Hourly tick; once per week. For every active stock record: units ISSUED in the last 30 and 90 days, from the l |
