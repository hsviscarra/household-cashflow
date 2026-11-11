"""ADR-072: where each account's data stands, and bank sync covering its days."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, LoadLog, Transaction
from app.services import status
from app.services.status import AccountTimeline, Gap, TimelineStatement

TODAY = date(2026, 11, 11)


def _acc(i: int, name: str, institution: str, sync: str | None = None) -> Account:
    return Account(
        account_id=i,
        name=name,
        institution=institution,
        kind="checking",
        owner="Hernan",
        country="EC",
        is_active=True,
        sync_id=sync,
    )


def _line(
    i: int, name: str, stmts: list[tuple[date, date, str]], gaps: list[Gap]
) -> AccountTimeline:
    return AccountTimeline(
        i,
        name,
        None,
        None,
        1,
        [TimelineStatement(1, "x.pdf", a, b, st, None) for a, b, st in stmts],
        gaps,
    )


def test_each_account_says_how_its_data_arrives_and_where_it_stands() -> None:
    accounts = [
        _acc(1, "Diners Club Hernan", "Diners Club"),
        _acc(2, "Produbanco Ahorros Hernan", "Produbanco"),
        _acc(3, "Banco Pichincha", "Banco Pichincha"),
        _acc(4, "BofA Adv Plus Banking", "Bank of America", sync="S1"),
        _acc(5, "Produbanco Lauren", "Produbanco"),
        _acc(6, "PacifiCard", "Pacificard"),
    ]
    timeline = [
        # Closed Nov 3, email not here a week later: late.
        _line(
            1,
            "Diners Club Hernan",
            [(date(2026, 9, 4), date(2026, 10, 3), "loaded")],
            [Gap(date(2026, 10, 4), TODAY, None, [date(2026, 11, 3)])],
        ),
        # Closed Oct 31, uploaded by hand: waiting on you.
        _line(
            2,
            "Produbanco Ahorros Hernan",
            [(date(2026, 10, 1), date(2026, 10, 31), "loaded")],
            [Gap(date(2026, 11, 1), date(2026, 11, 30), None, [date(2026, 10, 31)])],
        ),
        # Closed Nov 8: the email has until Nov 15.
        _line(
            3,
            "Banco Pichincha",
            [(date(2026, 9, 9), date(2026, 10, 8), "loaded")],
            [Gap(date(2026, 10, 9), TODAY, None, [date(2026, 11, 8)])],
        ),
        # Synced through today.
        _line(4, "BofA Adv Plus Banking", [(date(2026, 9, 1), TODAY, "synced")], []),
        # Uploaded, not approved.
        _line(
            5,
            "Produbanco Lauren",
            [(date(2026, 10, 1), date(2026, 10, 31), "loaded")],
            [Gap(date(2026, 11, 1), date(2026, 11, 30), None, [date(2026, 11, 30)])],
        ),
        # Current cycle, not issued yet.
        _line(
            6,
            "PacifiCard",
            [(date(2026, 9, 24), date(2026, 10, 23), "loaded")],
            [Gap(date(2026, 10, 24), TODAY, date(2026, 11, 23), [date(2026, 11, 23)])],
        ),
    ]
    waiting = {5: [(date(2026, 11, 1), date(2026, 11, 30), "not read yet")]}
    got = {x.name: x for x in status.sources(accounts, timeline, waiting, TODAY)}
    assert got["Diners Club Hernan"].how == "email" and got["Diners Club Hernan"].state == "late"
    assert "Gmail script" in got["Diners Club Hernan"].note
    assert got["Produbanco Ahorros Hernan"].state == "you_upload"
    assert got["Produbanco Ahorros Hernan"].note.startswith("Download the statement closing Oct 31")
    assert got["Banco Pichincha"].state == "on_its_way"
    assert got["Banco Pichincha"].expected == date(2026, 11, 15)
    assert got["BofA Adv Plus Banking"].how == "bank_sync"
    assert got["BofA Adv Plus Banking"].state == "up_to_date"
    assert got["Produbanco Lauren"].state == "on_import"
    assert got["PacifiCard"].state == "on_its_way" and got["PacifiCard"].expected == date(
        2026, 11, 23
    )
    order = [x.state for x in status.sources(accounts, timeline, waiting, TODAY)]
    assert order[0] == "late" and order[-1] == "up_to_date"


def test_bank_sync_covers_its_days(db: Session) -> None:
    acc = db.scalars(select(Account).where(Account.last4 == "8872")).one()
    acc.sync_id = "S1"
    db.add(
        Transaction(
            natural_key="k-sync-1",
            account_id=acc.account_id,
            txn_date=date(2026, 9, 2),
            cash_month=date(2026, 9, 1),
            amount=Decimal("-5"),
            description_raw="COFFEE",
            type="expense",
            source="bank_sync",
            status="pending",
        )
    )
    db.add(
        LoadLog(
            source="bank_sync",
            loaded_by="t",
            rows_loaded=1,
            summary="{}",
            loaded_at=datetime(2026, 11, 10, 6),
        )
    )
    db.commit()
    cov = status.sync_coverage(db, [acc], TODAY)
    assert cov[acc.account_id] == (date(2026, 9, 2), TODAY)
    # A sync a week old covers only up to its own day.
    assert status.sync_coverage(db, [acc], date(2026, 11, 20))[acc.account_id][1] == date(
        2026, 11, 10
    )


def test_net_worth_uses_the_synced_balance(db: Session) -> None:
    """ADR-073: a synced account's balance is the bank's, as of the sync."""
    import json

    from app.services import networth

    acc = db.scalars(select(Account).where(Account.last4 == "8872")).one()
    acc.sync_id = "S1"
    summary = {"accounts": [{"sync_id": "S1", "balance": "2000.00", "balance_date": "2026-11-10"}]}
    db.add(
        LoadLog(
            source="bank_sync",
            loaded_by="t",
            rows_loaded=0,
            summary=json.dumps(summary),
            loaded_at=datetime(2026, 11, 10, 6),
        )
    )
    db.commit()
    [item] = [i for i in networth.accounts(db, TODAY) if i.account_id == acc.account_id]
    assert item.value == Decimal("2000.00") and item.as_of == date(2026, 11, 10)
    assert item.source == "bank_sync"
    assert networth.accounts(db, date(2026, 11, 9)) == [] or all(
        i.account_id != acc.account_id for i in networth.accounts(db, date(2026, 11, 9))
    )
