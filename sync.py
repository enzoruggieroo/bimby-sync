"""Tiene la lista della spesa di Cookidoo allineata alla "Mia settimana".

1. Allinea la lista della spesa di Cookidoo alle ricette pianificate da oggi in
   avanti: aggiunge quelle mancanti, toglie quelle non più pianificate.
2. Le righe spuntate in Promemoria (input "comprati") vengono segnate in Cookidoo
   come "già in casa", così spariscono dalla lista esportata dall'app.

Il repository è pubblico: i log riportano solo quanti elementi sono cambiati,
mai i nomi di ricette o prodotti.
"""

import asyncio
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

import aiohttp
from cookidoo_api import Cookidoo
from cookidoo_api.helpers import get_localization_options
from cookidoo_api.types import CookidooConfig, CookidooIngredientItem

TIMEZONE = ZoneInfo("Europe/Rome")

# Quante settimane in avanti leggere dal calendario (una richiesta ciascuna).
WEEKS_AHEAD = 4

# Le ricette del catalogo hanno id tipo "r214846"; quelle create da te sono ULID.
CATALOG_RECIPE_ID = re.compile(r"^r\d+$")

# Cookidoo in italiano scrive "80 g di carota": il nome arriva come "di carota".
NAME_PREFIX = re.compile(r"^(?:di\s+|d['’]\s*)", re.IGNORECASE)

_LOGGER = logging.getLogger("bimby-sync")


def is_catalog_recipe(recipe_id: str) -> bool:
    return CATALOG_RECIPE_ID.match(recipe_id) is not None


async def planned_recipes(cookidoo: Cookidoo, today: date) -> set[str]:
    """Ricette pianificate da oggi in avanti."""
    days = {}
    for week in range(WEEKS_AHEAD):
        for day in await cookidoo.get_recipes_in_calendar_week(today + timedelta(weeks=week)):
            days[day.id] = day

    planned: set[str] = set()
    for day in days.values():
        try:
            day_date = date.fromisoformat(day.id)
        except ValueError as err:
            # Meglio non toccare nulla che togliere ricette per un formato inatteso.
            raise RuntimeError("Giorno del calendario in un formato non riconosciuto") from err
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

    _LOGGER.info("Ricette pianificate: %d · da aggiungere: %d · da togliere: %d",
                 len(planned), len(to_add), len(to_remove))
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


def ingredient_core(name: str) -> str:
    """Nome confrontabile: senza "di", in minuscolo, senza la preparazione dopo la virgola."""
    name = NAME_PREFIX.sub("", name.strip()).lower()
    return " ".join(name.split(",")[0].split())


def matches_line(line: str, item: CookidooIngredientItem) -> bool:
    """La riga esportata dall'app ("80 g di carota") parla di questo ingrediente?"""
    core = ingredient_core(item.name)
    if not core:
        return False
    text = " ".join(line.strip().lower().split())
    return re.search(rf"(?:^|[\s'’]){re.escape(core)}(?:$|,)", text) is not None


async def mark_bought(cookidoo: Cookidoo, bought: list[str], dry_run: bool) -> list[CookidooIngredientItem]:
    """Segna come "già in casa" gli ingredienti delle righe spuntate in Promemoria."""
    items = [item for item in await cookidoo.get_ingredient_items() if not item.is_owned]
    to_mark: dict[str, CookidooIngredientItem] = {}
    not_found = 0
    for line in bought:
        found = [item for item in items if matches_line(line, item)]
        not_found += not found
        to_mark.update((item.id, item) for item in found)

    _LOGGER.info("Righe spuntate: %d · riconosciute: %d · non trovate: %d · ingredienti segnati: %d",
                 len(bought), len(bought) - not_found, not_found, len(to_mark))
    if to_mark and not dry_run:
        await cookidoo.edit_ingredient_items_ownership(
            [replace(item, is_owned=True) for item in to_mark.values()]
        )
    return list(to_mark.values())


async def run(cookidoo: Cookidoo, today: date, dry_run: bool, bought: Iterable[str] = ()) -> None:
    planned = await planned_recipes(cookidoo, today)
    await sync_shopping_list(cookidoo, planned, dry_run)
    if bought := list(bought):
        await mark_bought(cookidoo, bought, dry_run)
    if dry_run:
        _LOGGER.info("Prova a secco: nessuna modifica fatta.")


def bought_text() -> str:
    """Righe spuntate in Promemoria, mandate dal Comando Rapido "Spesa" come input "comprati".

    Si leggono dal file dell'evento di GitHub e non da una variabile d'ambiente,
    perché GitHub stampa le variabili del passo nel log, che nel repository pubblico
    è visibile a tutti.
    """
    if event_path := os.environ.get("GITHUB_EVENT_PATH"):
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        return str((event.get("inputs") or {}).get("comprati") or "")
    return os.environ.get("COMPRATI", "")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    email = os.environ.get("COOKIDOO_EMAIL")
    password = os.environ.get("COOKIDOO_PASSWORD")
    if not email or not password:
        sys.exit("Mancano COOKIDOO_EMAIL e/o COOKIDOO_PASSWORD nei Secrets del repository.")
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    bought = [line.strip() for line in bought_text().splitlines() if line.strip()]

    localization = (await get_localization_options(country="it", language="it-IT"))[0]
    # CookieJar(unsafe=True) serve al login di Cookidoo (redirect tra domini).
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        cookidoo = Cookidoo(
            session,
            cfg=CookidooConfig(email=email, password=password, localization=localization),
        )
        await cookidoo.login()
        await run(cookidoo, datetime.now(TIMEZONE).date(), dry_run, bought)


if __name__ == "__main__":
    asyncio.run(main())
