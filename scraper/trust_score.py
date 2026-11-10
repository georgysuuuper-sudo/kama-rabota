# -*- coding: utf-8 -*-
"""Рейтинг доверия 0–100 по таблице из ТЗ (п. 4.4).

Базовый балл 40, сумма сигналов, итог ограничен 0–100.
Сигналы возвращаются вместе с баллом — сайт показывает их в карточке.
"""
from __future__ import annotations

import statistics
from collections import defaultdict

import config as C
import filters as F

W = C.TRUST_WEIGHTS


def build_medians(vacs: list[dict]) -> dict[tuple[str, str], float]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for v in vacs:
        value = F.monthly_from(v)
        if not value:
            continue
        cat, _ = F.categorize(v)
        groups[(cat, v.get("experience") or "unknown")].append(value)
    return {k: statistics.median(vals) for k, vals in groups.items() if len(vals) >= 3}


def _signal(label: str, delta: int) -> dict:
    return {"label": label, "delta": delta}


def score(v: dict, ctx: dict) -> tuple[int, list[dict]]:
    now = ctx.get("now")
    signals: list[dict] = []
    total = C.TRUST_BASE
    emp = v.get("employer") or {}

    def add(key: str, label: str):
        nonlocal total
        delta = W[key]
        total += delta
        signals.append(_signal(label, delta))

    if emp.get("trusted") or emp.get("accredited_it"):
        add("employer_trusted", "Работодатель проверен на hh.ru")

    if F.is_known_employer(v, ctx.get("employer_counts", {})):
        add("employer_known", "Известная компания, не однодневка")

    if F.description_is_full(v):
        add("description_full", "Подробное описание: обязанности и требования")

    if F.has_address(v):
        add("address_present", "Указан конкретный адрес или район")

    medians = ctx.get("medians", {})
    cat, _ = F.categorize(v)
    median = medians.get((cat, v.get("experience") or "unknown"))
    value = F.monthly_from(v) or 0
    inflated = False
    if v.get("experience") == "noExperience" and value:
        if median and value > C.SALARY_INFLATED_RATIO * median:
            inflated = True
        elif value > C.SALARY_ABSURD_LIMIT:
            inflated = True
    if inflated:
        add("salary_inflated", "Зарплата подозрительно выше рынка для этой роли")
    else:
        add("salary_realistic", "Зарплата в рынке для этой роли")

    if F.has_social_package(v):
        add("social_package", "Оформление по ТК РФ или соцпакет")

    if F.is_anonymous_employer(v):
        add("employer_anonymous", "Работодатель — частное лицо, без названия компании")

    desc_len = len(F.norm(v.get("description_text")))
    if 0 < desc_len < C.DESCRIPTION_SHORT_LEN:
        add("description_short", "Слишком короткое описание")

    soft = F.soft_stop_hits(v)
    if soft:
        add("soft_stop_word", "Тревожные формулировки: " + ", ".join(soft[:3]))

    if str(v.get("id")) in ctx.get("clone_ids", set()):
        add("clone_text", "Текст совпадает с вакансиями других «компаний»")

    total = max(0, min(100, total))
    signals.sort(key=lambda s: -abs(s["delta"]))
    return total, signals


def score_all(vacs: list[dict], now=None) -> list[dict]:
    ctx = {
        "now": now,
        "medians": build_medians(vacs),
        "employer_counts": F.employer_counts(vacs),
        "clone_ids": F.find_clones(vacs),
    }
    for v in vacs:
        value, signals = score(v, ctx)
        v["trust_score"] = value
        v["trust_signals"] = signals
    return vacs