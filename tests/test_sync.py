"""Test con un Cookidoo finto (nessuna rete)."""

import asyncio
from datetime import date, timedelta
import json

import pytest
from cookidoo_api.types import (
    CookidooCalendarDay,
    CookidooCalendarDayRecipe,
    CookidooIngredientItem,
)

import sync
from sync import matches_line

CUSTOM_ID = "01K2CVHD1DXG1PVETNVV3JPKWW"
TODAY = date(2026, 10, 20)  # martedì


def day(day_id: str, *recipe_ids: str, custom: tuple[str, ...] = ()) -> CookidooCalendarDay:
    return CookidooCalendarDay(
        id=day_id,
        title=day_id,
        recipes=[
            CookidooCalendarDayRecipe(
                id=i, name=i, total_time=0, thumbnail=None, image=None, url=""
            )
            for i in recipe_ids
        ],
        customer_recipe_ids=list(custom),
    )


class FakeRecipe:
    def __init__(self, recipe_id: str) -> None:
        self.id = recipe_id


class FakeCookidoo:
    def __init__(self, weeks: dict[date, list[CookidooCalendarDay]], in_list: list[str]) -> None:
        self.weeks = weeks
        self.in_list = list(in_list)
        self.calls: list[tuple[str, list[str]]] = []

    async def get_recipes_in_calendar_week(self, day: date) -> list[CookidooCalendarDay]:
        return self.weeks.get(day, [])

    async def get_shopping_list_recipes(self) -> list[FakeRecipe]:
        return [FakeRecipe(i) for i in self.in_list]

    async def add_ingredient_items_for_recipes(self, ids: list[str]) -> None:
        self.calls.append(("add", ids))

    async def add_ingredient_items_for_custom_recipes(self, ids: list[str]) -> None:
        self.calls.append(("add_custom", ids))

    async def remove_ingredient_items_for_recipes(self, ids: list[str]) -> None:
        self.calls.append(("remove", ids))

    async def remove_ingredient_items_for_custom_recipes(self, ids: list[str]) -> None:
        self.calls.append(("remove_custom", ids))


def calendar() -> dict[date, list[CookidooCalendarDay]]:
    return {
        TODAY: [
            day("2026-10-19", "r1"),  # ieri: escluso
            day("2026-10-20", "r2"),
            day("2026-10-22", "r3", custom=(CUSTOM_ID,)),
        ],
        TODAY + timedelta(weeks=1): [
            day("2026-10-27", "r4"),  # settimana prossima
        ],
    }


def test_run_adds_planned_and_removes_past_or_unplanned() -> None:
    fake = FakeCookidoo(calendar(), in_list=["r1", "r3", "r8"])
    asyncio.run(sync.run(fake, TODAY, dry_run=False))

    assert ("add", ["r2", "r4"]) in fake.calls
    assert ("add_custom", [CUSTOM_ID]) in fake.calls
    assert ("remove", ["r1", "r8"]) in fake.calls  # r1 è di ieri, r8 non è pianificata


def test_dry_run_changes_nothing() -> None:
    fake = FakeCookidoo(calendar(), in_list=["r8"])
    asyncio.run(sync.run(fake, TODAY, dry_run=True))
    assert fake.calls == []


def test_unknown_day_format_aborts_without_changes() -> None:
    fake = FakeCookidoo({TODAY: [day("martedì", "r2")]}, in_list=["r8"])
    with pytest.raises(RuntimeError):
        asyncio.run(sync.run(fake, TODAY, dry_run=False))
    assert fake.calls == []


def test_logs_never_contain_names(caplog) -> None:
    caplog.set_level("INFO")
    asyncio.run(sync.run(FakeCookidoo(calendar(), in_list=["r8"]), TODAY, dry_run=True))
    asyncio.run(sync.mark_bought(FakePantry(PANTRY), ["2 pizzichi di pepe", "1 kg di farina"], dry_run=True))
    text = caplog.text.lower()
    for secret in ["r2", "r8", CUSTOM_ID.lower(), "pepe", "farina"]:
        assert secret not in text


def test_bought_text_reads_event_file(tmp_path, monkeypatch) -> None:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"inputs": {"comprati": "80 g di carota\n1 limone"}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert sync.bought_text() == "80 g di carota\n1 limone"

    event.write_text(json.dumps({"schedule": "7,37 4-21 * * *"}), encoding="utf-8")
    assert sync.bought_text() == ""


def item(item_id: str, name: str, description: str = "", is_owned: bool = False) -> CookidooIngredientItem:
    return CookidooIngredientItem(id=item_id, name=name, is_owned=is_owned, description=description)


PANTRY = [
    item("1", "di olio extravergine di oliva", "80 g"),
    item("2", "Olio extravergine di oliva", "30 g"),
    item("3", "pepe", "1 pizzico"),
    item("4", "pepe nero macinato", "2 pizzichi"),
    item("5", "aglio", "2 spicchi"),
    item("6", "basilico fresco, le foglie lavate ed asciugate", "1 mazzetto"),
    item("7", "sale", "1 cucchiaino"),
    item("8", "carota", "80 g", is_owned=True),
]


class FakePantry:
    def __init__(self, items: list[CookidooIngredientItem]) -> None:
        self.items = items
        self.edited: list[CookidooIngredientItem] = []

    async def get_ingredient_items(self) -> list[CookidooIngredientItem]:
        return self.items

    async def edit_ingredient_items_ownership(self, items: list[CookidooIngredientItem]) -> None:
        self.edited += items


def test_matches_line_uses_whole_words_at_end() -> None:
    assert matches_line("110 g di olio extravergine di oliva", PANTRY[0])
    assert matches_line("110 g di olio extravergine di oliva", PANTRY[1])
    assert matches_line("2 pizzichi di pepe", PANTRY[2])
    assert not matches_line("3 pizzichi di pepe nero macinato", PANTRY[2])
    assert matches_line("3 pizzichi di pepe nero macinato", PANTRY[3])
    assert matches_line("2 spicchi d'aglio", PANTRY[4])
    assert matches_line("1 mazzetto di basilico fresco", PANTRY[5])
    assert matches_line("1 mazzetto di basilico fresco, le foglie lavate ed asciugate", PANTRY[5])
    assert not matches_line("2 cucchiaini di sale grosso", PANTRY[6])


def test_mark_bought_sets_owned_on_every_matching_item() -> None:
    pantry = FakePantry(PANTRY)
    lines = ["110 g di olio extravergine di oliva", "2 pizzichi di pepe", "80 g di carota", "1 kg di farina"]
    marked = asyncio.run(sync.mark_bought(pantry, lines, dry_run=False))

    assert sorted(i.id for i in marked) == ["1", "2", "3"]  # la carota è già in casa, la farina non c'è
    assert all(i.is_owned for i in pantry.edited)
    assert sorted(i.id for i in pantry.edited) == ["1", "2", "3"]


def test_mark_bought_dry_run_changes_nothing() -> None:
    pantry = FakePantry(PANTRY)
    asyncio.run(sync.mark_bought(pantry, ["2 pizzichi di pepe"], dry_run=True))
    assert pantry.edited == []
