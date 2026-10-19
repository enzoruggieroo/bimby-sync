"""Test con un Cookidoo finto (nessuna rete)."""

import asyncio
from collections import Counter
from datetime import date, timedelta

import pytest
from cookidoo_api.types import (
    CookidooCalendarDay,
    CookidooCalendarDayRecipe,
    CookidooIngredient,
    CookidooShoppingRecipe,
)

import sync
from sync import format_amount, parse_quantity, shopping_lines

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


def shopping_recipe(recipe_id: str, *ingredients: tuple[str, str]) -> CookidooShoppingRecipe:
    return CookidooShoppingRecipe(
        id=recipe_id,
        name=recipe_id,
        ingredients=[
            CookidooIngredient(id=name, name=name, description=description)
            for name, description in ingredients
        ],
        thumbnail=None,
        image=None,
        url="",
    )


class FakeCookidoo:
    def __init__(self, weeks: dict[date, list[CookidooCalendarDay]], recipes: dict[str, CookidooShoppingRecipe], in_list: list[str]) -> None:
        self.weeks = weeks
        self.recipes = recipes
        self.in_list = list(in_list)
        self.calls: list[tuple[str, list[str]]] = []

    async def get_recipes_in_calendar_week(self, day: date) -> list[CookidooCalendarDay]:
        return self.weeks.get(day, [])

    async def get_shopping_list_recipes(self) -> list[CookidooShoppingRecipe]:
        return [self.recipes[i] for i in self.in_list]

    async def add_ingredient_items_for_recipes(self, ids: list[str]) -> None:
        self.calls.append(("add", ids))
        self.in_list += ids

    async def add_ingredient_items_for_custom_recipes(self, ids: list[str]) -> None:
        self.calls.append(("add_custom", ids))
        self.in_list += ids

    async def remove_ingredient_items_for_recipes(self, ids: list[str]) -> None:
        self.calls.append(("remove", ids))
        self.in_list = [i for i in self.in_list if i not in ids]

    async def remove_ingredient_items_for_custom_recipes(self, ids: list[str]) -> None:
        self.calls.append(("remove_custom", ids))
        self.in_list = [i for i in self.in_list if i not in ids]


RECIPES = {
    "r1": shopping_recipe("r1", ("cipolla", "1"), ("olio", "20 g")),
    "r2": shopping_recipe("r2", ("cipolla", "2"), ("pasta", "320 g"), ("sale", "")),
    "r3": shopping_recipe("r3", ("pasta", "400 g"), ("lenticchie", "250 g")),
    "r8": shopping_recipe("r8", ("zucchero", "100 g")),
    CUSTOM_ID: shopping_recipe(CUSTOM_ID, ("olio", "40 - 60 g")),
}


def calendar() -> dict[date, list[CookidooCalendarDay]]:
    return {
        TODAY: [
            day("2026-10-19", "r1"),  # ieri: escluso
            day("2026-10-20", "r2"),
            day("2026-10-22", "r3", custom=(CUSTOM_ID,)),
        ],
        TODAY + timedelta(weeks=1): [
            day("2026-10-27", "r2"),  # settimana prossima, stessa ricetta di oggi
        ],
    }


@pytest.fixture(autouse=True)
def output_file(tmp_path, monkeypatch):
    path = tmp_path / "spesa.txt"
    monkeypatch.setattr(sync, "OUTPUT_FILE", path)
    return path


def test_run_syncs_cookidoo_and_writes_summed_list(output_file) -> None:
    fake = FakeCookidoo(calendar(), RECIPES, in_list=["r1", "r3", "r8"])
    lines = asyncio.run(sync.run(fake, TODAY, dry_run=False))

    assert ("add", ["r2"]) in fake.calls
    assert ("add_custom", [CUSTOM_ID]) in fake.calls
    assert ("remove", ["r1", "r8"]) in fake.calls
    # r2 è pianificata due volte: cipolla 2+2, pasta 320+320+400.
    assert lines == [
        "Cipolla – 4",
        "Lenticchie – 250 g",
        "Olio – 60 g",
        "Pasta – 1,04 kg",
        "Sale",
    ]
    assert output_file.read_text(encoding="utf-8") == "\n".join(lines) + "\n"


def test_dry_run_changes_nothing(output_file) -> None:
    fake = FakeCookidoo(calendar(), RECIPES, in_list=["r8"])
    asyncio.run(sync.run(fake, TODAY, dry_run=True))
    assert fake.calls == []
    assert not output_file.exists()


def test_unknown_day_format_aborts_without_changes(output_file) -> None:
    fake = FakeCookidoo({TODAY: [day("martedì", "r2")]}, RECIPES, in_list=["r8"])
    with pytest.raises(RuntimeError):
        asyncio.run(sync.run(fake, TODAY, dry_run=False))
    assert fake.calls == []
    assert not output_file.exists()


def test_parse_quantity() -> None:
    assert parse_quantity("200 g") == (200, "g")
    assert parse_quantity("4") == (4, "")
    assert parse_quantity("1.5 l") == (1.5, "l")
    assert parse_quantity("40 - 60 g") == (60, "g")
    assert parse_quantity("2 cucchiai") == (2, "cucchiaio")
    assert parse_quantity("") is None


def test_same_name_different_units_stay_separate() -> None:
    recipes = [
        shopping_recipe("r1", ("Cipolla", "1"), ("parmigiano", "1 cucchiaio")),
        shopping_recipe("r2", ("cipolla", "50 g"), ("Parmigiano", "2 cucchiai")),
    ]
    assert shopping_lines(recipes, Counter({"r1": 1, "r2": 1})) == [
        "Cipolla – 1",
        "Cipolla – 50 g",
        "Parmigiano – 3 cucchiai",
    ]


def test_italian_prefix_is_removed_and_water_skipped() -> None:
    recipes = [
        shopping_recipe("r1", ("di olio extravergine di oliva", "80 g"), ("di acqua", "1000 g")),
        shopping_recipe("r2", ("Olio extravergine di oliva", "30 g"), ("d'aglio", "1 spicchio")),
    ]
    assert shopping_lines(recipes, Counter({"r1": 1, "r2": 1})) == [
        "Aglio – 1 spicchio",
        "Olio extravergine di oliva – 110 g",
    ]


def test_format_amount() -> None:
    assert format_amount(1500, "ml") == "1,5 l"
    assert format_amount(0.5, "cucchiaino") == "0,5 cucchiaino"
    assert format_amount(3, "spicchio") == "3 spicchi"
