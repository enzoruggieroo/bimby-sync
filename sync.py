"""Prepara la lista della spesa dalle ricette della "Mia settimana" di Cookidoo.

1. Allinea la lista della spesa di Cookidoo alle ricette pianificate da oggi in
   avanti: aggiunge quelle mancanti, toglie quelle non più pianificate.
2. Somma gli ingredienti di tutte le ricette (una ricetta pianificata due volte
   conta due volte) e scrive il risultato in spesa.txt, una riga per prodotto.
   Il Comando Rapido sull'iPhone legge quel file e lo porta in Promemoria.
"""

import asyncio
from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, timedelta
import logging
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

import aiohttp
from cookidoo_api import Cookidoo
from cookidoo_api.helpers import get_localization_options
from cookidoo_api.types import CookidooConfig, CookidooShoppingRecipe

TIMEZONE = ZoneInfo("Europe/Rome")
OUTPUT_FILE = Path(__file__).with_name("spesa.txt")

# Quante settimane in avanti leggere dal calendario (una richiesta ciascuna).
WEEKS_AHEAD = 4

# Le ricette del catalogo hanno id tipo "r214846"; quelle create da te sono ULID.
CATALOG_RECIPE_ID = re.compile(r"^r\d+$")

# "200 g", "4", "1.5 l", "40 - 60 g" (di un intervallo si compra il massimo).
QUANTITY = re.compile(
    r"^\s*(?P<low>\d+(?:[.,]\d+)?)(?:\s*-\s*(?P<high>\d+(?:[.,]\d+)?))?\s*(?P<unit>.*?)\s*$"
)

# Unità al singolare -> plurale. Servono a sommare "1 cucchiaio" con "2 cucchiai".
UNIT_PLURALS = {
    "bustina": "bustine",
    "confezione": "confezioni",
    "cubetto": "cubetti",
    "cucchiaino": "cucchiaini",
    "cucchiaio": "cucchiai",
    "fetta": "fette",
    "foglia": "foglie",
    "lattina": "lattine",
    "mazzetto": "mazzetti",
    "pizzico": "pizzichi",
    "rametto": "rametti",
    "spicchio": "spicchi",
    "vasetto": "vasetti",
}
UNIT_SINGULARS = {plural: singular for singular, plural in UNIT_PLURALS.items()}

# Cookidoo in italiano scrive "80 g di carota": il nome arriva come "di carota".
NAME_PREFIX = re.compile(r"^(?:di\s+|d['’]\s*)", re.IGNORECASE)

# Ingredienti che non si comprano.
SKIPPED_INGREDIENTS = {"acqua"}

_LOGGER = logging.getLogger("bimby-sync")


def is_catalog_recipe(recipe_id: str) -> bool:
    return CATALOG_RECIPE_ID.match(recipe_id) is not None


async def planned_recipes(cookidoo: Cookidoo, today: date) -> Counter[str]:
    """Quante volte è pianificata ogni ricetta, da oggi in avanti."""
    days = {}
    for week in range(WEEKS_AHEAD):
        for day in await cookidoo.get_recipes_in_calendar_week(today + timedelta(weeks=week)):
            days[day.id] = day

    planned: Counter[str] = Counter()
    for day in days.values():
        try:
            day_date = date.fromisoformat(day.id)
        except ValueError as err:
            # Meglio non toccare nulla che togliere ricette per un formato inatteso.
            raise RuntimeError(f"Giorno del calendario non riconosciuto: {day.id!r}") from err
        if day_date >= today:
            planned.update(recipe.id for recipe in day.recipes)
            planned.update(day.customer_recipe_ids)
    return planned


async def sync_shopping_list(
    cookidoo: Cookidoo, planned: Iterable[str], dry_run: bool
) -> tuple[set[str], set[str]]:
    """Allinea le ricette nella lista di Cookidoo a quelle pianificate."""
    planned = set(planned)
    in_list = {recipe.id for recipe in await cookidoo.get_shopping_list_recipes()}
    to_add = planned - in_list
    to_remove = in_list - planned

    _LOGGER.info("Ricette da aggiungere alla lista Cookidoo: %s", sorted(to_add) or "nessuna")
    _LOGGER.info("Ricette da togliere dalla lista Cookidoo: %s", sorted(to_remove) or "nessuna")
    if dry_run:
        return to_add, to_remove

    if catalog := sorted(filter(is_catalog_recipe, to_add)):
        await cookidoo.add_ingredient_items_for_recipes(catalog)
    if custom := sorted(to_add - set(catalog)):
        await cookidoo.add_ingredient_items_for_custom_recipes(custom)
    if catalog := sorted(filter(is_catalog_recipe, to_remove)):
        await cookidoo.remove_ingredient_items_for_recipes(catalog)
    if custom := sorted(to_remove - set(catalog)):
        await cookidoo.remove_ingredient_items_for_custom_recipes(custom)
    return to_add, to_remove


def parse_quantity(description: str) -> tuple[float, str] | None:
    """(quantità, unità al singolare) oppure None se non c'è una quantità ("q.b.")."""
    match = QUANTITY.match(description)
    if match is None:
        return None
    amount = float((match["high"] or match["low"]).replace(",", "."))
    unit = match["unit"]
    return amount, UNIT_SINGULARS.get(unit, unit)


def format_amount(amount: float, unit: str) -> str:
    if unit == "g" and amount >= 1000:
        amount, unit = amount / 1000, "kg"
    elif unit == "ml" and amount >= 1000:
        amount, unit = amount / 1000, "l"
    number = f"{amount:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    if amount > 1:
        unit = UNIT_PLURALS.get(unit, unit)
    return f"{number} {unit}".strip()


def shopping_lines(recipes: Iterable[CookidooShoppingRecipe], planned: Counter[str]) -> list[str]:
    """Una riga per prodotto, con le quantità sommate per nome e unità."""
    names: dict[str, str] = {}
    totals: dict[str, dict[str, float]] = {}
    for recipe in recipes:
        for _ in range(planned[recipe.id]):
            for ingredient in recipe.ingredients:
                name = NAME_PREFIX.sub("", ingredient.name.strip())
                key = name.lower()
                if key in SKIPPED_INGREDIENTS:
                    continue
                names.setdefault(key, name)
                amounts = totals.setdefault(key, {})
                if (quantity := parse_quantity(ingredient.description)) is not None:
                    amount, unit = quantity
                    amounts[unit] = amounts.get(unit, 0) + amount

    lines = []
    for key in sorted(totals):
        name = names[key][:1].upper() + names[key][1:]
        if not totals[key]:
            lines.append(name)
        for unit, amount in sorted(totals[key].items()):
            lines.append(f"{name} – {format_amount(amount, unit)}")
    return lines


async def run(cookidoo: Cookidoo, today: date, dry_run: bool) -> list[str]:
    planned = await planned_recipes(cookidoo, today)
    _LOGGER.info("Ricette pianificate da %s in poi: %s", today, dict(planned) or "nessuna")
    await sync_shopping_list(cookidoo, planned, dry_run)

    lines = shopping_lines(await cookidoo.get_shopping_list_recipes(), planned)
    _LOGGER.info("Lista della spesa (%d prodotti):\n%s", len(lines), "\n".join(lines))
    if dry_run:
        _LOGGER.info("Prova a secco: nessuna modifica fatta.")
    else:
        OUTPUT_FILE.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return lines


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    email = os.environ.get("COOKIDOO_EMAIL")
    password = os.environ.get("COOKIDOO_PASSWORD")
    if not email or not password:
        sys.exit("Mancano COOKIDOO_EMAIL e/o COOKIDOO_PASSWORD nei Secrets del repository.")
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"

    localization = (await get_localization_options(country="it", language="it-IT"))[0]
    # CookieJar(unsafe=True) serve al login di Cookidoo (redirect tra domini).
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        cookidoo = Cookidoo(
            session,
            cfg=CookidooConfig(email=email, password=password, localization=localization),
        )
        await cookidoo.login()
        await run(cookidoo, datetime.now(TIMEZONE).date(), dry_run)


if __name__ == "__main__":
    asyncio.run(main())
