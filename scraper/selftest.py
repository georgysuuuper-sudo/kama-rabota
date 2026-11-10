# -*- coding: utf-8 -*-
"""
Автотест приёмки (ТЗ, раздел 10).
Проверяет data/vacancies.json: гео, свежесть, зарплату, стоп-листы,
рейтинг доверия, уникальность, ссылки и отсутствие личных данных.
Запуск: python scraper/selftest.py   (код возврата 1 = провал)
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as C
import filters as F

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

REQUIRED = ["id", "title", "url", "published_at", "employer", "experience",
            "category", "trust_score"]
PHONE = re.compile(r"(?:\+7|8)[\s(-]?\d{3}[\s)-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
HH_URL = re.compile(r"^https://([a-z0-9-]+\.)?hh\.ru/vacancy/\d+")


def to_raw(r):
    """Публичная запись -> форма, которую понимают filters.py."""
    return {
        "id": r.get("id"),
        "title": r.get("title"),
        "employer": r.get("employer") or {},
        "salary": {"from": r.get("salary_from"), "to": r.get("salary_to"),
                   "currency": C.CURRENCY, "gross": r.get("salary_gross")},
        "published_at": r.get("published_at"),
        "area": {"id": C.AREA_ID, "name": C.AREA_NAME},
        "address": r.get("address") or {},
        "work_formats": r.get("work_formats") or [],
        "schedule": r.get("schedule"),
        "employment": r.get("employment"),
        "experience": r.get("experience"),
        "key_skills": r.get("key_skills") or [],
        "description_text": r.get("snippet") or "",
    }


def main():
    vac_path, meta_path = DATA / "vacancies.json", DATA / "meta.json"
    if not vac_path.exists() or not meta_path.exists():
        print("ПРОВАЛ: нет data/vacancies.json или data/meta.json")
        return 1

    vacs = json.loads(vac_path.read_text("utf-8"))
    meta = json.loads(meta_path.read_text("utf-8"))
    collected_at = F.parse_dt(meta.get("updated_at")) or datetime.now(timezone.utc)
    trust_min = meta.get("trust_min", C.TRUST_MIN)

    errors, warnings = [], []

    def err(msg):
        errors.append(msg)

    if not isinstance(vacs, list) or not vacs:
        print("ПРОВАЛ: выдача пуста")
        return 1

    ids = [str(v.get("id")) for v in vacs]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        err(f"дубли id: {sorted(dupes)[:10]}")

    stop_hits = 0
    for v in vacs:
        vid = v.get("id")
        label = f"[{vid}] {str(v.get('title'))[:60]}"

        missing = [k for k in REQUIRED if v.get(k) in (None, "", {})]
        if not v.get("salary_from") and not v.get("salary_to"):
            missing.append("salary_from/salary_to")
        if missing:
            err(f"{label}: нет полей {missing}")

        raw = to_raw(v)

        hard = F.hard_reject(raw, collected_at)
        if hard:
            err(f"{label}: жёсткое условие -> {hard}")

        reason = (F.gender_reject(raw) or F.scam_reject(raw)
                  or F.manual_review(raw) or F.geo_reject(raw))
        if reason:
            stop_hits += 1
            err(f"{label}: стоп-лист -> {reason}")

        score = v.get("trust_score", 0)
        if not isinstance(score, int) or not 0 <= score <= 100:
            err(f"{label}: некорректный trust_score {score!r}")
        elif score < trust_min:
            err(f"{label}: trust_score {score} < {trust_min}")

        if v.get("category") not in C.CATEGORY_ORDER:
            err(f"{label}: неизвестная категория {v.get('category')!r}")

        url = v.get("url") or ""
        if not HH_URL.match(url):
            err(f"{label}: ссылка не на hh.ru -> {url[:80]}")
        elif str(vid) not in url:
            err(f"{label}: id вакансии не совпадает со ссылкой")

        emp = v.get("employer") or {}
        if not emp.get("name"):
            err(f"{label}: работодатель без названия")

        snippet = v.get("snippet") or ""
        if len(snippet) > C.SNIPPET_MAX_LEN + 1:
            err(f"{label}: сниппет длиннее {C.SNIPPET_MAX_LEN} символов ({len(snippet)})")

        blob = " ".join(str(x) for x in [v.get("title"), snippet, emp.get("name"),
                                         " ".join(v.get("tags") or []),
                                         " ".join(v.get("key_skills") or [])])
        if PHONE.search(blob) or EMAIL.search(blob):
            err(f"{label}: в выдаче личные данные / контакты работодателя")
        if v.get("description_text") or v.get("description"):
            err(f"{label}: сохранено полное описание (запрещено ТЗ п.9)")

    if len(vacs) < C.MIN_VACANCIES:
        warnings.append(f"в выдаче {len(vacs)} вакансий, ТЗ хочет >= {C.MIN_VACANCIES}")

    stale_h = (datetime.now(timezone.utc) - collected_at).total_seconds() / 3600
    if stale_h > C.STALE_DATA_HOURS:
        warnings.append(f"данные устарели: {stale_h:.1f} ч. с последнего сбора")

    no_exp = sum(1 for v in vacs if v.get("experience") == "noExperience")
    hot = sum(1 for v in vacs if v.get("is_hot"))
    trusted = sum(1 for v in vacs if (v.get("employer") or {}).get("trusted"))
    scores = sorted(v.get("trust_score", 0) for v in vacs)
    median = scores[len(scores) // 2]

    print("=" * 64)
    print("АВТОТЕСТ ПРИЁМКИ · Кама.Работа")
    print("=" * 64)
    print(f"Вакансий в выдаче      : {len(vacs)}")
    print(f"Без опыта              : {no_exp}")
    print(f"Новых за 24 ч          : {hot}")
    print(f"Проверенных работодателей: {trusted}")
    print(f"trust_score min/median/max: {scores[0]}/{median}/{scores[-1]}")
    print(f"Источник / порог       : {meta.get('source')} / {trust_min}")
    print(f"Собрано                : {meta.get('updated_at')} ({stale_h:.1f} ч. назад)")
    print(f"Проверок на вакансию   : 12, всего {len(vacs) * 12}")
    print(f"Попаданий в стоп-листы : {stop_hits}")
    print("-" * 64)
    for w in warnings:
        print(f"ПРЕДУПРЕЖДЕНИЕ: {w}")
    if errors:
        for e in errors[:40]:
            print(f"ОШИБКА: {e}")
        if len(errors) > 40:
            print(f"... и ещё {len(errors) - 40}")
        print(f"\nПРОВАЛ: {len(errors)} нарушений")
        return 1
    print("\nOK: все проверки пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(main())