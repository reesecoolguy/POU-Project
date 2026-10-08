"""The SQL variant's POSTING PATTERN, executed on SQLite (docs/alt/PostMovement.sql is the T-SQL twin and is NOT executed here).

Proves the pattern: one transaction (lock/validate/update/append), unique RequestID replay, unique (StockKey, SeqNo), last-unit race, rollback on a crash between the two writes."""
import sqlite3
import threading
import uuid

import pytest


def mkdb(path):
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.executescript("""
    CREATE TABLE StockLocation (StockKey TEXT PRIMARY KEY, OnHandQty INTEGER, StockVersion INTEGER NOT NULL DEFAULT 0, CHECK (OnHandQty IS NULL OR OnHandQty >= 0));
    CREATE TABLE Ledger (LedgerId INTEGER PRIMARY KEY AUTOINCREMENT, RequestID TEXT NOT NULL UNIQUE, StockKey TEXT NOT NULL, SeqNo INTEGER NOT NULL,
                         LedgerType TEXT, QtyDelta INTEGER, QtyBefore INTEGER, QtyAfter INTEGER NOT NULL, UNIQUE (StockKey, SeqNo));
    INSERT INTO StockLocation VALUES ('A|1', 1, 1);
    INSERT INTO Ledger (RequestID, StockKey, SeqNo, LedgerType, QtyAfter) VALUES ('open', 'A|1', 1, 'OPENING', 1);
    """)
    return db


def post(path, rid, typ, key, qty, crash_between=False):
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        db.execute("BEGIN IMMEDIATE")                                             # = UPDLOCK, HOLDLOCK on the row
        if db.execute("SELECT 1 FROM Ledger WHERE RequestID=?", (rid,)).fetchone():
            r = db.execute("SELECT QtyAfter FROM Ledger WHERE RequestID=?", (rid,)).fetchone()
            db.execute("COMMIT"); return ("Succeeded", "REPLAY", r[0])
        before, ver = db.execute("SELECT OnHandQty, StockVersion FROM StockLocation WHERE StockKey=?", (key,)).fetchone()
        if typ == "ISSUE" and qty > before:
            db.execute("ROLLBACK"); return ("Rejected", "INSUFFICIENT_STOCK", before)
        after = before - qty if typ == "ISSUE" else before + qty
        n = db.execute("UPDATE StockLocation SET OnHandQty=?, StockVersion=? WHERE StockKey=? AND StockVersion=?", (after, ver + 1, key, ver)).rowcount
        assert n == 1
        if crash_between:
            raise RuntimeError("crash between stock update and ledger append")
        db.execute("INSERT INTO Ledger (RequestID, StockKey, SeqNo, LedgerType, QtyDelta, QtyBefore, QtyAfter) VALUES (?,?,?,?,?,?,?)",
                   (rid, key, ver + 1, typ, after - before, before, after))
        db.execute("COMMIT"); return ("Succeeded", "OK", after)
    except Exception:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def test_two_operators_one_last_unit(tmp_path):
    path = str(tmp_path / "t.db"); mkdb(path).close()
    out = []
    ts = [threading.Thread(target=lambda: out.append(post(path, str(uuid.uuid4()), "ISSUE", "A|1", 1))) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(o[0] for o in out) == ["Rejected"] * 7 + ["Succeeded"]
    db = sqlite3.connect(path)
    assert db.execute("SELECT OnHandQty, StockVersion FROM StockLocation").fetchone() == (0, 2)
    assert db.execute("SELECT COUNT(*) FROM Ledger").fetchone()[0] == 2


def test_replayed_request_posts_once(tmp_path):
    path = str(tmp_path / "t.db"); db = mkdb(path); db.execute("UPDATE StockLocation SET OnHandQty=10"); db.close()
    rid = str(uuid.uuid4())
    assert post(path, rid, "ISSUE", "A|1", 3) == ("Succeeded", "OK", 7)
    assert post(path, rid, "ISSUE", "A|1", 3) == ("Succeeded", "REPLAY", 7)
    assert sqlite3.connect(path).execute("SELECT OnHandQty FROM StockLocation").fetchone()[0] == 7


def test_crash_between_stock_update_and_ledger_append_rolls_both_back(tmp_path):
    path = str(tmp_path / "t.db"); db = mkdb(path); db.execute("UPDATE StockLocation SET OnHandQty=10"); db.close()
    with pytest.raises(RuntimeError):
        post(path, str(uuid.uuid4()), "ISSUE", "A|1", 3, crash_between=True)
    db = sqlite3.connect(path)
    assert db.execute("SELECT OnHandQty, StockVersion FROM StockLocation").fetchone() == (10, 1)       # nothing changed, and that IS established
    assert db.execute("SELECT COUNT(*) FROM Ledger").fetchone()[0] == 1
