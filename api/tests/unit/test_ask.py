"""ADR-100: a question answered from the read-only tools, counted against the month's cap."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services import ask
from app.services.ask import Tool, Turn

D = Decimal
TODAY = date(2026, 11, 13)
USER = "hernan@example.com"


def _tools(calls: list[dict[str, Any]]) -> list[Tool]:
    def cash_flow(from_month: str, to_month: str) -> list[dict[str, str]]:
        calls.append({"from_month": from_month, "to_month": to_month})
        if from_month == "bad":
            raise ValueError("Months look like 2026-10, not 'bad'.")
        return [{"month": "2026-10", "expenses": "4200.00"}]

    return [Tool("cash_flow", "Cash flow by month.", {"type": "object"}, cash_flow)]


def _script(*turns: Turn) -> tuple[ask.Caller, list[dict[str, Any]]]:
    """A stand-in for Claude that plays the given turns and keeps what it was sent."""
    left = list(turns)
    seen: list[dict[str, Any]] = []

    def call(model: str, system: str, tools: list[Tool], messages: list[dict[str, Any]]) -> Turn:
        seen.append({"model": model, "system": system, "messages": [*messages]})
        return left.pop(0)

    return call, seen


def _wants(arguments: dict[str, Any], tokens: tuple[int, int] = (1000, 100)) -> Turn:
    return Turn("", [("t1", "cash_flow", arguments)], *tokens, content=[{"type": "tool_use"}])


def test_what_a_question_costs() -> None:
    # 1,000,000 tokens in and 100,000 out on the small model: 0.10 + 0.05.
    assert ask.cost_of("claude-haiku-5-5", 1_000_000, 100_000) == D("0.15")
    assert ask.cost_of("claude-sonnet-5-5", 10_000, 1_000) == D("0.03")
    # A model the table doesn't know is charged at the dearest.
    assert ask.cost_of("some-new-model", 10_000, 1_000) == D("0.03")


def test_a_question_uses_the_tools_and_is_counted(db: Session) -> None:
    calls: list[dict[str, Any]] = []
    call, seen = _script(
        _wants({"from_month": "2026-10", "to_month": "2026-10"}),
        Turn("October cost $4,200.00.", [], 2000, 200),
    )
    a = ask.ask(
        db,
        "  How much did we spend in October? ",
        USER,
        today=TODAY,
        page="/spending",
        month="2026-10",
        call=call,
        tools=_tools(calls),
    )
    assert a.text == "October cost $4,200.00." and a.tools_used == ["cash_flow"]
    assert calls == [{"from_month": "2026-10", "to_month": "2026-10"}]
    # 3,000 tokens in and 300 out on the small model: 0.0003 + 0.00015.
    assert a.cost == D("0.00045") and a.usage.spent == D("0.00045") and a.usage.questions == 1
    assert (a.usage.cap, a.usage.left) == (D(10), D("9.99955"))
    first, second = seen
    assert first["model"] == "claude-haiku-5-5" and "Today is 2026-11-13" in first["system"]
    assert "on the page /spending, looking at 2026-10." in first["system"]
    assert first["messages"] == [{"role": "user", "content": "How much did we spend in October?"}]
    # The tool's result went back to Claude as data.
    result = second["messages"][-1]["content"][0]
    assert (result["type"], result["tool_use_id"], result["is_error"]) == (
        "tool_result",
        "t1",
        False,
    )
    assert '"expenses": "4200.00"' in result["content"]

    # The larger model when asked to think harder; the month's total keeps adding up.
    call, seen = _script(Turn("In short: fine.", [], 10_000, 1_000))
    deep = ask.ask(db, "Why?", USER, today=TODAY, deep=True, call=call, tools=[])
    assert seen[0]["model"] == "claude-sonnet-5-5" and deep.cost == D("0.03")
    assert deep.usage.spent == D("0.03045") and deep.usage.questions == 2
    assert ask.usage(db, date(2026, 12, 1)).spent == 0  # a new month starts from zero


def test_a_tool_that_fails_is_told_to_claude_and_too_many_lookups_stop(db: Session) -> None:
    calls: list[dict[str, Any]] = []
    tools = {t.name: t for t in _tools(calls)}
    assert ask.run_tool(tools, "cash_flow", {"from_month": "bad", "to_month": "x"}) == (
        "cash_flow could not answer: Months look like 2026-10, not 'bad'.",
        True,
    )
    assert ask.run_tool(tools, "cash_flow", {"nope": 1})[1] is True  # wrong arguments
    assert ask.run_tool(tools, "delete_everything", {}) == (
        "There is no tool called delete_everything.",
        True,
    )
    long = Tool("big", "", {}, lambda: "x" * (ask.MAX_TOOL_CHARS + 50))
    text, failed = ask.run_tool({"big": long}, "big", {})
    assert not failed and text.endswith("[cut: ask for less, a month or a category]")

    # Claude keeps asking for tools: after MAX_TURNS it is stopped, and what it used is counted.
    turn = _wants({"from_month": "2026-10", "to_month": "2026-10"})
    call, seen = _script(*[turn] * ask.MAX_TURNS)
    a = ask.ask(db, "Everything?", USER, today=TODAY, call=call, tools=list(tools.values()))
    assert len(seen) == ask.MAX_TURNS and "more lookups than one question allows" in a.text
    assert a.usage.questions == 1 and a.cost == ask.cost_of("claude-haiku-5-5", 6000, 600).quantize(
        ask.USD
    )


def test_the_cap(db: Session) -> None:
    assert ask.cap(db) == D(10)
    ask.set_cap(db, D("0.01"), USER)
    call, _ = _script(Turn("Yes.", [], 100_000, 10_000), Turn("No.", [], 1, 1))
    first = ask.ask(db, "One?", USER, today=TODAY, call=call, tools=[])
    assert first.usage.spent == D("0.015") and first.usage.left == 0  # over by the last question
    with pytest.raises(ask.AskError, match=r"limit for Claude \(\$0.01\) is used up") as stopped:
        ask.ask(db, "Two?", USER, today=TODAY, call=call, tools=[])
    assert stopped.value.status == 429
    ask.set_cap(db, D(0), USER)
    with pytest.raises(ask.AskError, match="turned off"):
        ask.ask(db, "Three?", USER, today=TODAY, call=call, tools=[])
    with pytest.raises(ask.AskError, match="can't be negative"):
        ask.set_cap(db, D(-1), USER)
    with pytest.raises(ask.AskError, match="between 1 and"):
        ask.ask(db, "   ", USER, today=TODAY, call=call, tools=[])
    # Settings that can't be read fall back: the default cap, a month counted from zero.
    row = db.get(AppSetting, ask.CAP_KEY)
    assert row is not None
    row.setting_value = "lots"
    db.add(AppSetting(setting_key=ask.USAGE_KEY + "2027-01", setting_value="{", updated_by=USER))
    db.commit()
    assert ask.cap(db) == D(10) and ask.usage(db, date(2027, 1, 5)).spent == 0


def test_the_tools_offered_are_the_reading_ones() -> None:
    names = {t.name for t in ask.read_tools()}
    assert {"cash_flow", "spending_by_category", "balance_sheet", "bills"} <= names
    assert "save_portfolio" not in names
    assert all(t.schema.get("type") == "object" and callable(t.run) for t in ask.read_tools())
    prompt = ask.system_prompt(TODAY, None, None)
    assert "They are on the page" not in prompt and "never instructions" in prompt


def test_the_api(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    usage = client.get("/api/ask/usage", params={"today": "2026-11-13"}).json()
    assert usage == {
        "available": False,
        "month": "2026-11-01",
        "spent": "0",
        "questions": 0,
        "cap": "10",
        "left": "10",
    }
    # Without an API key there is nothing to ask.
    no_key = client.post("/api/ask", json={"question": "Hello?"})
    assert no_key.status_code == 503 and "no API key" in no_key.json()["detail"]

    monkeypatch.setattr(ask, "available", lambda: True)
    monkeypatch.setattr(
        ask, "call_claude", lambda *_: Turn("About $4,200.00 in October.", [], 3000, 300)
    )
    monkeypatch.setattr(ask, "read_tools", lambda: [])
    out = client.post(
        "/api/ask",
        params={"today": "2026-11-13"},
        json={"question": "October?", "page": "/spending", "month": "2026-10"},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["answer"] == "About $4,200.00 in October." and body["cost"] == "0.000450"
    assert body["usage"]["questions"] == 1 and body["usage"]["available"] is True

    capped = client.put("/api/ask/cap", params={"today": "2026-11-13"}, json={"cap": "0"}).json()
    assert capped["cap"] == "0" and capped["left"] == "0"
    assert client.post("/api/ask", json={"question": "Again?"}).status_code == 429
    assert client.put("/api/ask/cap", json={"cap": "-5"}).status_code == 422
    assert (
        client.post("/api/ask", json={"question": "x", "page": "javascript:1"}).status_code == 422
    )
