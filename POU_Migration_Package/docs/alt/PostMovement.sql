/*
  SMALLEST ALTERNATIVE: Azure SQL / SQL Server version of the posting core.            STATUS: GENERATED, NOT EXECUTED on SQL Server.
  (No SQL Server was available while this package was built. The same logic IS exercised, step for step, on SQLite in
  tests/test_sql_alternative.py - last-unit race, replayed request, crash between steps - which proves the PATTERN, not this T-SQL's syntax.)

  What it replaces: the 16-call SharePoint protocol in POU-ProcessRequest. One transaction:
     replay check -> lock the stock row -> validate -> update stock -> append ledger -> done   (all or nothing)
  Authentication/authorisation (session, badge, supervisor) is still decided by the caller (a flow) and passed in as parameters;
  grant EXECUTE on dbo.PostMovement to the flow's identity ONLY, and deny INSERT/UPDATE/DELETE on the tables to everyone else.
*/
CREATE TABLE dbo.StockLocation (
    StockKey      nvarchar(200) NOT NULL CONSTRAINT PK_StockLocation PRIMARY KEY,
    ItemID        nvarchar(100) NOT NULL,
    LocationCode  nvarchar(50)  NOT NULL,
    OnHandQty     int           NULL,                     -- NULL = no verified balance (never 0 by default)
    StockVersion  int           NOT NULL CONSTRAINT DF_SL_ver DEFAULT 0,
    BalanceStatus varchar(12)   NOT NULL CONSTRAINT DF_SL_bal DEFAULT 'NoBalance',
    MinQty        int           NULL,
    MaxQty        int           NULL,
    Active        bit           NOT NULL CONSTRAINT DF_SL_act DEFAULT 1,
    CONSTRAINT CK_SL_nonneg CHECK (OnHandQty IS NULL OR OnHandQty >= 0)
);

CREATE TABLE dbo.Ledger (
    LedgerId     bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Ledger PRIMARY KEY,
    RequestID    uniqueidentifier NOT NULL CONSTRAINT UQ_Ledger_Request UNIQUE,       -- duplicate protection
    StockKey     nvarchar(200) NOT NULL CONSTRAINT FK_Ledger_Stock REFERENCES dbo.StockLocation(StockKey),
    SeqNo        int           NOT NULL,
    LedgerType   varchar(12)   NOT NULL,
    QtyDelta     int           NULL,
    QtyBefore    int           NULL,
    QtyAfter     int           NOT NULL,
    BadgeID      nvarchar(100) NULL,
    EmployeeName nvarchar(200) NULL,
    StationID    nvarchar(50)  NULL,
    AuthorizedBy nvarchar(320) NULL,
    OccurredUtc  datetime2(0)  NOT NULL CONSTRAINT DF_Ledger_t DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Ledger_Seq UNIQUE (StockKey, SeqNo)                                  -- the compare-and-swap, as a constraint
);
GO

CREATE OR ALTER PROCEDURE dbo.PostMovement
    @RequestID uniqueidentifier, @Type varchar(12), @StockKey nvarchar(200), @Qty int,
    @ExpectedVersion int = NULL, @BadgeID nvarchar(100) = NULL, @EmployeeName nvarchar(200) = NULL,
    @StationID nvarchar(50) = NULL, @AuthorizedBy nvarchar(320) = NULL
AS
BEGIN
    SET NOCOUNT ON; SET XACT_ABORT ON;
    DECLARE @before int, @ver int, @after int, @delta int, @active bit;

    BEGIN TRAN;
    -- 1. replay: the same RequestID returns the stored outcome and changes nothing
    IF EXISTS (SELECT 1 FROM dbo.Ledger WHERE RequestID = @RequestID)
    BEGIN
        SELECT 'Succeeded' AS Status, 'REPLAY' AS Code, QtyAfter AS NewOnHand FROM dbo.Ledger WHERE RequestID = @RequestID;
        COMMIT; RETURN;
    END

    -- 2. lock the one stock row for the rest of the transaction (two operators are serialised here)
    SELECT @before = OnHandQty, @ver = StockVersion, @active = Active
      FROM dbo.StockLocation WITH (UPDLOCK, HOLDLOCK) WHERE StockKey = @StockKey;
    IF @ver IS NULL        BEGIN ROLLBACK; SELECT 'Rejected' AS Status, 'STOCK_NOT_FOUND' AS Code; RETURN; END
    IF @active = 0         BEGIN ROLLBACK; SELECT 'Rejected', 'STOCK_INACTIVE'; RETURN; END

    -- 3. validate (same rules as the flow)
    IF @Type IN ('ISSUE','RECEIPT') AND (@Qty IS NULL OR @Qty < 1)         BEGIN ROLLBACK; SELECT 'Rejected', 'INVALID_QUANTITY'; RETURN; END
    IF @Type IN ('ISSUE','RECEIPT','ADJUSTMENT') AND @before IS NULL       BEGIN ROLLBACK; SELECT 'Rejected', 'NO_BALANCE'; RETURN; END
    IF @Type = 'ISSUE' AND @Qty > @before                                  BEGIN ROLLBACK; SELECT 'Rejected', 'INSUFFICIENT_STOCK'; RETURN; END
    IF @Type = 'AUDIT' AND (@ExpectedVersion IS NULL OR @ExpectedVersion <> @ver) BEGIN ROLLBACK; SELECT 'Rejected', 'STALE_COUNT'; RETURN; END
    IF @Type = 'OPENING' AND NOT (@before IS NULL AND @ver = 0)            BEGIN ROLLBACK; SELECT 'Rejected', 'OPENING_NOT_ALLOWED'; RETURN; END

    SET @after = CASE @Type WHEN 'ISSUE' THEN @before - @Qty WHEN 'RECEIPT' THEN @before + @Qty ELSE @Qty END;
    SET @delta = CASE WHEN @before IS NULL THEN NULL ELSE @after - @before END;

    -- 4. update + append in the SAME transaction: either both happen or neither
    UPDATE dbo.StockLocation
       SET OnHandQty = @after, StockVersion = @ver + 1,
           BalanceStatus = CASE @Type WHEN 'AUDIT' THEN 'Verified' WHEN 'OPENING' THEN 'Unverified' ELSE BalanceStatus END
     WHERE StockKey = @StockKey AND StockVersion = @ver;
    IF @@ROWCOUNT <> 1 BEGIN ROLLBACK; SELECT 'Failed' AS Status, 'CONTENTION'; RETURN; END

    INSERT dbo.Ledger (RequestID, StockKey, SeqNo, LedgerType, QtyDelta, QtyBefore, QtyAfter, BadgeID, EmployeeName, StationID, AuthorizedBy)
    VALUES (@RequestID, @StockKey, @ver + 1, @Type, @delta, @before, @after, @BadgeID, @EmployeeName, @StationID, @AuthorizedBy);
    COMMIT;
    SELECT 'Succeeded' AS Status, 'OK' AS Code, @after AS NewOnHand;
END
GO
-- Make the ledger append-only for everyone, including the application login:
--   DENY UPDATE, DELETE ON dbo.Ledger TO <app login>;   and  REVOKE INSERT/UPDATE/DELETE on dbo.StockLocation (writes only through the procedure).
