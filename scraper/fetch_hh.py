# -*- coding: utf-8 -*-
"""Сборщик вакансий «Кама.Работа».

Приоритет — официальный API hh.ru. Если он недоступен (403/400/429), берём
HTML-выдачу perm.hh.ru и вытаскиваем HH-Lux-InitialState. Между запросами пауза,
на 429/5xx — экспоненциальная задержка. Сырые записи кэшируются в .cache/,
поэтому фильтры можно перенастраивать без повторной нагрузки на hh.ru.

Запуск:
    python scraper/fetch_hh.py                 # полный прогон
    python scraper/fetch_hh.py --offline       # пересобрать выдачу из кэша
    python scraper/fetch_hh.py --no-details    # без догрузки описаний
    python scraper/fetch_hh.py --source html   # только HTML-выдача

Результат: data/vacancies.json и data/meta.json.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as C          # noqa: E402
import filters as F         # noqa: E402
import trust_score as T     # noqa: E402

try:
    import requests
except ImportError:         # curl есть и в Windows, и в ubuntu-latest
    requests = None

DATA = ROOT / "data"
CACHE = HERE / ".cache"
RAW_CACHE = CACHE / "raw.json"
REJECT_CACHE = CACHE / "rejected.json"
VERSION = "1.0.0"
MSK = timezone(timedelta(hours=5))


def log(*args):
    print(*args, flush=True)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Client:
    def __init__(self, source: str = "auto"):
        self.source = source
        self.requests_done = 0
        self.api_ok = None
        self.session = requests.Session() if requests else None
        self.token = os.environ.get(C.HH_TOKEN_ENV, "").strip()

    def _headers(self, api: bool) -> dict:
        h = {
            "User-Agent": C.USER_AGENT if api else C.BROWSER_UA,
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        }
        if api:
            h["Accept"] = "application/json"
            if self.token:
                h["Authorization"] = f"Bearer {self.token}"
        else:
            h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            h["Referer"] = C.SITE_BASE + "/"
        return h

    def get(self, url: str, api: bool = False) -> str | None:
        headers = self._headers(api)
        delay = C.RETRY_BACKOFF
        for attempt in range(C.MAX_RETRIES):
            self.requests_done += 1
            status, body = self._once(url, headers)
            if status == 200 and body:
                return body
            if status in (400, 403) and api:
                return None                      # API закрыт — молча уходим на HTML
            if status in (429, 500, 502, 503, 504, 406, 0) and attempt < C.MAX_RETRIES - 1:
                log(f"  HTTP {status or 'timeout'} -> пауза {delay:.0f}s ({url[:70]})")
                time.sleep(delay)
                delay *= 2
                continue
            return None
        return None

    def _once(self, url: str, headers: dict) -> tuple[int, str]:
        if self.session is not None:
            try:
                r = self.session.get(url, headers=headers, timeout=C.REQUEST_TIMEOUT)
                return r.status_code, r.text
            except Exception as exc:
                log(f"  requests: {type(exc).__name__}")
                return 0, ""
        curl = shutil.which("curl")
        if not curl:
            return 0, ""
        cmd = [curl, "-s", "--compressed", "--max-time", str(C.REQUEST_TIMEOUT), url,
               "-w", "\n%{http_code}"]
        for k, val in headers.items():
            cmd += ["-H", f"{k}: {val}"]
        try:
            r = subprocess.run(cmd, capture_output=True)
        except Exception:
            return 0, ""
        if r.returncode != 0:
            return 0, ""
        text = r.stdout.decode("utf-8", errors="replace")
        idx = text.rfind("\n")
        code = text[idx + 1:].strip() if idx >= 0 else ""
        body = text[:idx] if idx >= 0 else text
        try:
            return int(code), body
        except ValueError:
            return 0, body

    def json(self, url: str) -> dict | None:
        body = self.get(url, api=True)
        if not body:
            return None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def pause(self):
        time.sleep(random.uniform(*C.REQUEST_PAUSE))


# --------------------------------------------------------------------------
# Нормализация: общий внутренний формат
# --------------------------------------------------------------------------

def _flatten(items, key: str) -> list[str]:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            val = it.get(key)
            if isinstance(val, list):
                out.extend(str(x) for x in val)
            elif val:
                out.append(str(val))
        elif isinstance(it, str):
            out.append(it)
    return out


def _labels(items) -> list[str]:
    out = []
    for it in items or []:
        if isinstance(it, dict):
            out.append(str(it.get("text") or it.get("name") or it.get("id") or ""))
        else:
            out.append(str(it))
    return [x for x in out if x]


def _logo(company: dict) -> str | None:
    logos = ((company.get("logos") or {}).get("logo")) or []
    for it in logos:
        if isinstance(it, dict) and it.get("@type") in ("small", "medium", "searchResultsPage"):
            url = it.get("@url") or ""
            if url.startswith("/"):
                return "https://img.hhcdn.ru" + url
            if url.startswith("http"):
                return url
    return None


def _address(addr: dict | None) -> dict:
    addr = addr or {}
    district = addr.get("district") or (addr.get("districtDto") or {}).get("name")
    metro = addr.get("metro")
    if not metro:
        stations = addr.get("metro_stations") or addr.get("metroStations") or []
        names = [s.get("station_name") or s.get("stationName") or s.get("name")
                 for s in stations if isinstance(s, dict)]
        metro = ", ".join(n for n in names if n) or None
    street = addr.get("street")
    building = addr.get("building")
    full = " ".join(str(x) for x in (street, building) if x) or None
    return {
        "city": addr.get("city") or (addr.get("area") or {}).get("name"),
        "street": full,
        "district": district,
        "metro": metro,
        "display": addr.get("displayName") or addr.get("raw") or full,
    }


def _salary(comp: dict | None) -> dict:
    comp = comp or {}
    return {
        "from": comp.get("from"),
        "to": comp.get("to"),
        "currency": comp.get("currency") or comp.get("currencyCode") or C.CURRENCY,
        "gross": bool(comp.get("gross")),
        "mode": comp.get("mode") or "MONTH",
        "unit_from": comp.get("perModeFrom"),
        "unit_to": comp.get("perModeTo"),
        "frequency": comp.get("frequency"),
    }


def _employer(company: dict | None, serp: bool) -> dict:
    company = company or {}
    if serp:
        cat = company.get("@category")
        rev = company.get("employerReviews") or {}
        rating, reviews = rev.get("totalRating"), rev.get("reviewsCount")
        trusted = bool(company.get("@trusted"))
        site = company.get("companySiteUrl")
        accredited = bool(company.get("accreditedITEmployer"))
        name = company.get("visibleName") or company.get("name")
        eid = company.get("id")
        logo = _logo(company)
    else:
        cat = company.get("type") or company.get("category")
        rating = company.get("rating")
        reviews = company.get("reviews_count")
        trusted = bool(company.get("trusted"))
        site = company.get("site_url")
        accredited = bool(company.get("accredited_it_employer"))
        name = company.get("name")
        eid = company.get("id")
        logo = (company.get("logo_urls") or {}).get("90")
    anonymous = cat in ("PRIVATE_INDIVIDUAL", "SELF_EMPLOYED") or not name \
        or bool(re.search(r"^(ищу сотрудника|частное лицо)", F.norm(name)))
    try:
        rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating = None
    return {
        "id": eid,
        "name": name,
        "url": f"{C.SITE_BASE}/employer/{eid}" if eid else company.get("alternate_url") or company.get("url"),
        "trusted": trusted,
        "category": cat,
        "anonymous": anonymous,
        "site": site,
        "logo": logo,
        "rating": rating,
        "reviews": int(reviews) if reviews else 0,
        "accredited_it": accredited,
    }


SCHEDULE_MAP = {"FULL_DAY": "fullDay", "SHIFT": "shift", "FLEXIBLE": "flexible",
                "REMOTE": "remote", "FLY_IN_FLY_OUT": "flyInFlyOut"}
EMPLOYMENT_MAP = {"FULL": "full", "PART": "part", "PROJECT": "project",
                  "PROBATION": "probation", "VOLUNTEER": "volunteer",
                  "FLY_IN_FLY_OUT": "flyInFlyOut"}


def normalize_serp(v: dict) -> dict:
    exp = v.get("workExperience")
    exp = exp.get("id") if isinstance(exp, dict) else exp
    formats = _flatten(v.get("workFormats"), "workFormatsElement")
    days = _flatten(v.get("workScheduleByDays"), "workScheduleByDaysElement")
    schedule = v.get("@workSchedule")
    if not schedule:
        schedule = "remote" if "REMOTE" in formats else "fullDay"
    employment = (v.get("employment") or {}).get("@type") or v.get("employmentForm") or "FULL"
    area = v.get("area") or {}
    pub = (v.get("publicationTime") or {}).get("$") or v.get("creationTime")
    vid = v.get("vacancyId")
    links = v.get("links") or {}
    return {
        "id": str(vid),
        "title": v.get("name"),
        "url": links.get("desktop") or f"{C.SITE_BASE}/vacancy/{vid}",
        "published_at": pub,
        "archived": bool(v.get("closedForApplicants")),
        "employer": _employer(v.get("company"), serp=True),
        "salary": _salary(v.get("compensation")),
        "employment": EMPLOYMENT_MAP.get(str(employment).upper(), str(employment).lower()),
        "schedule": SCHEDULE_MAP.get(str(schedule).upper(), schedule),
        "work_formats": [f.upper() for f in formats],
        "schedule_days": days,
        "experience": exp,
        "area": {"id": int(area["@id"]) if area.get("@id") else None, "name": area.get("name")},
        "address": _address(v.get("address")),
        "snippet": {},
        "description_html": None,
        "description_text": "",
        "key_skills": [],
        "labels": _labels(v.get("labels")),
        "hh_tags": _labels(v.get("tags")),
        "responses": v.get("responsesCount") or 0,
        "accept_temporary": bool(v.get("acceptTemporary")),
        "internship": bool(v.get("internship")),
        "night_shifts": bool(v.get("nightShifts")),
        "accept_labor_contract": bool(v.get("acceptLaborContract")),
        "professional_roles": _flatten(v.get("professionalRoleIds"), "professionalRoleId"),
        "is_adv": bool(v.get("@isAdv")),
        "contact_text": "",
        "origin": "html",
    }


def normalize_api(item: dict) -> dict:
    emp = item.get("employer") or {}
    employer = _employer(emp, serp=False)
    employer["url"] = emp.get("alternate_url") or employer["url"]
    sal = item.get("salary") or {}
    salary = _salary(sal)
    addr = item.get("address") or {}
    area = item.get("area") or {}
    schedule = (item.get("schedule") or {}).get("id")
    formats = [f.get("id") for f in item.get("work_format") or [] if isinstance(f, dict)]
    if not formats:
        formats = ["REMOTE"] if schedule == "remote" else ["ON_SITE"]
    return {
        "id": str(item.get("id")),
        "title": item.get("name"),
        "url": item.get("alternate_url") or f"{C.SITE_BASE}/vacancy/{item.get('id')}",
        "published_at": item.get("published_at"),
        "archived": bool(item.get("archived")),
        "employer": employer,
        "salary": salary,
        "employment": (item.get("employment") or {}).get("id") or "full",
        "schedule": schedule or "fullDay",
        "work_formats": [str(f).upper() for f in formats],
        "schedule_days": [str(d.get("id")) for d in item.get("work_schedule_by_days") or [] if isinstance(d, dict)],
        "experience": (item.get("experience") or {}).get("id"),
        "area": {"id": int(area["id"]) if str(area.get("id", "")).isdigit() else None, "name": area.get("name")},
        "address": _address(addr),
        "snippet": item.get("snippet") or {},
        "description_html": item.get("description"),
        "description_text": F.plain_text(item.get("description")),
        "key_skills": [s.get("name") for s in item.get("key_skills") or [] if isinstance(s, dict)],
        "labels": _labels(item.get("labels")),
        "hh_tags": [],
        "responses": 0,
        "accept_temporary": bool(item.get("accept_temporary")),
        "internship": bool(item.get("internship")),
        "night_shifts": bool(item.get("night_shifts")),
        "accept_labor_contract": bool(item.get("accept_labor_contract")),
        "professional_roles": [str(r.get("id")) for r in item.get("professional_roles") or [] if isinstance(r, dict)],
        "is_adv": False,
        "contact_text": "",
        "origin": "api",
    }


# --------------------------------------------------------------------------
# Поиск: API
# --------------------------------------------------------------------------

def fetch_api(client: Client, max_pages: int) -> list[dict]:
    base = dict(area=C.AREA_ID, period=C.PERIOD_DAYS, salary=C.MIN_SALARY,
                currency=C.CURRENCY, only_with_salary=str(C.ONLY_WITH_SALARY).lower(),
                per_page=C.PER_PAGE, order_by=C.ORDER_BY)
    out: dict[str, dict] = {}
    for extra in C.API_PASSES:
        params = {**base, **extra}
        query = "&".join(f"{k}={v}" for k, v in params.items())
        label = ",".join(f"{k}={v}" for k, v in extra.items()) or "all"
        got = 0
        for page in range(max_pages):
            data = client.json(f"{C.API_BASE}/vacancies?{query}&page={page}")
            if not data or "items" in data and not data["items"]:
                break
            items = data.get("items")
            if items is None:
                log(f"  API pass [{label}]: ответ без items, прекращаем")
                client.api_ok = False
                return list(out.values())
            client.api_ok = True
            new = 0
            for it in items:
                v = normalize_api(it)
                if v["id"] not in out:
                    out[v["id"]] = v
                    new += 1
            got += len(items)
            log(f"  API [{label}] page {page}: {len(items)} шт, новых {new} (всего {len(out)})")
            pages = data.get("pages") or 1
            client.pause()
            if new == 0 or page + 1 >= pages:
                break
        if got == 0:
            break
    return list(out.values())


# --------------------------------------------------------------------------
# Поиск: HTML-выдача
# --------------------------------------------------------------------------

def extract_state(page_html: str) -> dict | None:
    i = page_html.find("HH-Lux-InitialState")
    if i < 0:
        return None
    start = page_html.find(">", i) + 1
    end = page_html.find("</template>", start)
    if end < 0:
        return None
    try:
        return json.loads(html.unescape(page_html[start:end].strip()))
    except json.JSONDecodeError:
        return None


def search_url(page: int, extra: str = "") -> str:
    return (f"{C.SITE_BASE}/search/vacancy?area={C.AREA_ID}&only_with_salary=true"
            f"&salary={C.MIN_SALARY}&currency={C.CURRENCY}&period={C.PERIOD_DAYS}"
            f"&order_by={C.ORDER_BY}&page={page}{extra}")


def fetch_html(client: Client, max_pages: int) -> list[dict]:
    out: dict[str, dict] = {}
    for extra in C.HTML_PASSES:
        label = extra.strip("&") or "all"
        empty_streak = 0
        for page in range(max_pages):
            body = client.get(search_url(page, extra))
            if not body:
                log(f"  HTML [{label}] page {page}: не скачалось, пропуск прохода")
                break
            state = extract_state(body)
            if state is None:
                log(f"  HTML [{label}] page {page}: нет состояния (блок?), пропуск прохода")
                break
            items = (state.get("vacancySearchResult") or {}).get("vacancies") or []
            new = 0
            for it in items:
                if not it.get("vacancyId"):
                    continue
                v = normalize_serp(it)
                if v["id"] not in out:
                    out[v["id"]] = v
                    new += 1
            log(f"  HTML [{label}] page {page}: {len(items)} шт, новых {new} (всего {len(out)})")
            client.pause()
            if not items:
                break
            empty_streak = empty_streak + 1 if new == 0 else 0
            if empty_streak >= 2:
                break
    return list(out.values())


# --------------------------------------------------------------------------
# Обогащение описанием
# --------------------------------------------------------------------------

def apply_detail(v: dict, detail: dict) -> None:
    if not detail:
        return
    desc = detail.get("description")
    if desc:
        v["description_html"] = desc
        v["description_text"] = F.plain_text(desc)
    skills = detail.get("key_skills") or detail.get("keySkills") or []
    if skills:
        v["key_skills"] = [s.get("name") if isinstance(s, dict) else str(s) for s in skills]
    addr = detail.get("address")
    if addr:
        merged = _address(addr)
        for k, val in merged.items():
            if val:
                v["address"][k] = val
    if detail.get("snippet"):
        v["snippet"] = detail["snippet"]
    contact = detail.get("contactInfo") or detail.get("contact_info") or {}
    if isinstance(contact, dict):
        chunks = []
        for key in ("email", "phones", "contactPhones"):
            val = contact.get(key)
            if isinstance(val, list):
                chunks.extend(json.dumps(x, ensure_ascii=False) for x in val)
            elif val:
                chunks.append(str(val))
        v["contact_text"] = " ".join(chunks)
    for key, target in (("employmentForm", "employment"), ("workExperience", "experience")):
        val = detail.get(key)
        if isinstance(val, str) and val:
            v[target] = EMPLOYMENT_MAP.get(val.upper(), val) if key == "employmentForm" else val
    if isinstance(detail.get("workFormats"), list) and detail["workFormats"]:
        v["work_formats"] = [str(x).upper() for x in _flatten(detail["workFormats"], "workFormatsElement") or detail["workFormats"]]
    if detail.get("status"):
        status = detail["status"]
        if isinstance(status, dict) and status.get("id") in ("archived", "closed"):
            v["archived"] = True


def fetch_detail_html(client: Client, vid: str) -> dict | None:
    body = client.get(f"{C.SITE_BASE}/vacancy/{vid}")
    if not body:
        return None
    state = extract_state(body)
    if not state:
        return None
    full = ((state.get("vacancyView") or {}).get("vacancyFull") or {})
    vac = full.get("vacancy") or {}
    if not vac:
        return None
    extra = full.get("extraVacancyFields") or {}
    vac["labels"] = extra.get("labels") or vac.get("labels")
    return vac


def enrich(client: Client, vacs: list[dict], limit: int, source: str) -> int:
    done = 0
    for v in vacs:
        if done >= limit:
            break
        if v.get("description_text"):
            continue
        detail = None
        if source == "api":
            detail = client.json(f"{C.API_BASE}/vacancies/{v['id']}")
        if detail is None:
            detail = fetch_detail_html(client, v["id"])
        if detail:
            apply_detail(v, detail)
            done += 1
            if done % 25 == 0:
                log(f"  описаний загружено: {done}")
        client.pause()
    return done


# --------------------------------------------------------------------------
# Кэш сырых записей
# --------------------------------------------------------------------------

def load_cache() -> dict[str, dict]:
    if not RAW_CACHE.exists():
        return {}
    try:
        items = json.loads(RAW_CACHE.read_text("utf-8"))
        return {str(v["id"]): v for v in items if v.get("id")}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def save_cache(records: dict[str, dict], now: datetime) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    keep = []
    for v in records.values():
        dt = F.parse_dt(v.get("published_at"))
        if dt and (now - dt).total_seconds() / 86400 > C.PERIOD_DAYS + 2:
            continue
        keep.append(v)
    RAW_CACHE.write_text(json.dumps(keep, ensure_ascii=False), "utf-8")


def merge(old: dict[str, dict], fresh: list[dict]) -> dict[str, dict]:
    merged = dict(old)
    for v in fresh:
        prev = merged.get(v["id"])
        if prev is None:
            merged[v["id"]] = v
            continue
        # свежая запись важнее, но описание и адрес не теряем
        if not v.get("description_text") and prev.get("description_text"):
            v["description_html"] = prev.get("description_html")
            v["description_text"] = prev["description_text"]
            v["key_skills"] = prev.get("key_skills") or v.get("key_skills")
            v["snippet"] = prev.get("snippet") or v.get("snippet")
        for key, val in (prev.get("address") or {}).items():
            if val and not (v.get("address") or {}).get(key):
                v.setdefault("address", {})[key] = val
        merged[v["id"]] = v
    return merged


# --------------------------------------------------------------------------
# Сниппет и финальная запись
# --------------------------------------------------------------------------

SECTION_MARKERS = [
    r"обязанности", r"что нужно делать", r"чем предстоит заниматься", r"задачи",
    r"требования", r"что мы ждем", r"что мы ожидаем", r"наши ожидания",
    r"что предстоит делать", r"условия",
]


def snippet_from_description(v: dict) -> str:
    txt = v.get("description_text") or ""
    if not txt:
        return ""
    low = F.norm(txt)
    best = None
    for marker in SECTION_MARKERS:
        m = re.search(marker + r"[:\s]", low)
        if m and (best is None or m.start() < best):
            best = m.start()
    if best is not None:
        tail = txt[best:]
        tail = re.sub(r"^[^:]{0,40}:\s*", "", tail).strip()
        tail = re.sub(r"^[\s•·\-–—]+", "", tail)
        if len(tail) > 40:
            return tail
    return txt


def public_record(v: dict, now: datetime) -> dict:
    category, categories = F.categorize(v)
    age_h = F.age_days(v, now) * 24
    salary = v.get("salary") or {}
    addr = v.get("address") or {}
    emp = v.get("employer") or {}
    snippet = F.make_snippet(v)
    if not snippet:
        snippet = F.make_snippet({**v, "description_text": snippet_from_description(v)})
    rec = {
        "id": v["id"],
        "title": v.get("title"),
        "url": v.get("url"),
        "published_at": v.get("published_at"),
        "employer": {
            "name": emp.get("name"),
            "url": emp.get("url"),
            "trusted": bool(emp.get("trusted")),
            "logo": emp.get("logo"),
            "rating": emp.get("rating"),
            "reviews": emp.get("reviews") or 0,
            "category": emp.get("category"),
        },
        "salary_from": salary.get("from"),
        "salary_to": salary.get("to"),
        "salary_gross": bool(salary.get("gross")),
        "salary_mode": salary.get("mode") or "MONTH",
        "salary_unit_from": salary.get("unit_from"),
        "salary_unit_to": salary.get("unit_to"),
        "salary_frequency": salary.get("frequency"),
        "employment": EMPLOYMENT_MAP.get(str(v.get("employment") or "").upper(), v.get("employment")),
        "schedule": v.get("schedule"),
        "work_formats": v.get("work_formats") or [],
        "schedule_days": v.get("schedule_days") or [],
        "experience": v.get("experience"),
        "address": {k: addr.get(k) for k in ("city", "street", "district", "metro", "display")},
        "snippet": snippet,
        "category": category,
        "categories": categories,
        "trust_score": v.get("trust_score", 0),
        "trust_signals": v.get("trust_signals", []),
        "tags": F.make_tags(v),
        "is_new": age_h <= C.IS_NEW_WITHIN_HOURS,
        "is_hot": age_h <= C.NEW_WITHIN_HOURS,
        "description_len": len(v.get("description_text") or ""),
        "key_skills": (v.get("key_skills") or [])[:8],
        "labels": (v.get("labels") or [])[:4],
        "responses": v.get("responses") or 0,
    }
    if v.get("similar_count"):
        rec["similar_count"] = v["similar_count"]
    return {k: val for k, val in rec.items() if val not in (None, "", [])}


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def run(args) -> int:
    started = time.time()
    now = datetime.now(timezone.utc)
    DATA.mkdir(parents=True, exist_ok=True)
    client = Client(args.source)

    cached = load_cache()
    log(f"Кэш: {len(cached)} записей")
    fresh: list[dict] = []
    source = "cache"

    if not args.offline:
        if args.source in ("auto", "api"):
            log("Пробуем официальный API hh.ru…")
            fresh = fetch_api(client, args.pages)
            if fresh:
                source = "api"
        if not fresh and args.source in ("auto", "html"):
            log("API недоступен, переходим на HTML-выдачу perm.hh.ru…")
            fresh = fetch_html(client, args.pages)
            if fresh:
                source = "html"
        if not fresh and cached:
            log("Сеть недоступна — работаем из кэша")
        elif not fresh:
            log("Данные получить не удалось")
            return 1

    records = merge(cached, fresh)
    if not records:
        log("Пусто: ни сети, ни кэша")
        return 1
    save_cache(records, now)

    raw = list(records.values())
    log(f"Сырых записей: {len(raw)} (новых за прогон: {len(fresh)})")

    # 1. жёсткие условия и стоп-листы — до догрузки описаний, чтобы не качать лишнее
    candidates, rejected = [], []
    for v in raw:
        reason = F.reject_reason(v, now)
        if reason:
            rejected.append({"id": v["id"], "title": v.get("title"),
                             "employer": (v.get("employer") or {}).get("name"),
                             "url": v.get("url"), "reason": reason})
        else:
            candidates.append(v)
    log(f"Прошли предварительный отбор: {len(candidates)}, отсеяно: {len(rejected)}")

    # 2. описания
    if not args.no_details and not args.offline:
        need = [v for v in candidates if not v.get("description_text")]
        log(f"Догружаем описания: {len(need)} (лимит {args.limit_details})")
        got = enrich(client, candidates, args.limit_details, source)
        log(f"Описаний получено: {got}")
        save_cache(records, now)
        # после описаний стоп-листы могут сработать по тексту
        kept = []
        for v in candidates:
            reason = F.gender_reject(v) or F.scam_reject(v) or F.manual_review(v)
            if reason:
                rejected.append({"id": v["id"], "title": v.get("title"),
                                 "employer": (v.get("employer") or {}).get("name"),
                                 "url": v.get("url"), "reason": reason})
            else:
                kept.append(v)
        candidates = kept
        log(f"После проверки описаний: {len(candidates)}")

    # 3. дедупликация, клоны, рейтинг
    candidates = F.dedupe(candidates)
    candidates = F.collapse_employer(candidates)
    candidates = T.score_all(candidates, now)

    # 4. порог доверия
    trust_min = args.min_trust if args.min_trust is not None else C.TRUST_MIN
    passed = [v for v in candidates if v["trust_score"] >= trust_min]
    relaxed = False
    if len(passed) < C.MIN_VACANCIES and trust_min > C.TRUST_MIN_RELAXED:
        trust_min = C.TRUST_MIN_RELAXED
        passed = [v for v in candidates if v["trust_score"] >= trust_min]
        relaxed = True
        log(f"Меньше {C.MIN_VACANCIES} вакансий — порог доверия ослаблен до {trust_min}")
    for v in candidates:
        if v["trust_score"] < trust_min:
            rejected.append({"id": v["id"], "title": v.get("title"),
                             "employer": (v.get("employer") or {}).get("name"),
                             "url": v.get("url"),
                             "reason": f"рейтинг доверия {v['trust_score']} < {trust_min}"})

    # «без опыта» сверху, остальное ниже — как в ТЗ 4.6
    passed.sort(key=lambda v: (
        0 if v.get("experience") == "noExperience" else 1,
        -(F.parse_dt(v.get("published_at")) or now).timestamp(),
    ))

    published = [public_record(v, now) for v in passed]
    (DATA / "vacancies.json").write_text(
        json.dumps(published, ensure_ascii=False, separators=(",", ":")), "utf-8")

    reasons = Counter(r["reason"].split(":")[0] for r in rejected)
    cats = Counter()
    for v in published:
        cats.update(v.get("categories") or [v["category"]])
    new_today = sum(1 for v in published if v.get("is_hot"))
    next_update = now.replace(minute=0, second=0, microsecond=0)
    while next_update <= now:
        next_update += timedelta(hours=6)
    meta = {
        "version": VERSION,
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "next_update_at": next_update.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "area": C.AREA_NAME,
        "area_id": C.AREA_ID,
        "period_days": C.PERIOD_DAYS,
        "min_salary": C.MIN_SALARY,
        "currency": C.CURRENCY,
        "include_remote": C.INCLUDE_REMOTE,
        "trust_min": trust_min,
        "trust_relaxed": relaxed,
        "total_raw": len(raw),
        "total_candidates": len(candidates),
        "total_published": len(published),
        "total_rejected": len(rejected),
        "new_today": new_today,
        "new_48h": sum(1 for v in published if v.get("is_new")),
        "no_experience": sum(1 for v in published if v.get("experience") == "noExperience"),
        "with_description": sum(1 for v in published if v.get("description_len", 0) > 0),
        "median_salary": int(sorted(F.monthly_from(v) or 0 for v in passed)[len(passed) // 2]) if passed else 0,
        "categories": {k: cats.get(k, 0) for k in C.CATEGORY_ORDER},
        "rejected_reasons": dict(reasons.most_common()),
        "requests": client.requests_done,
        "duration_sec": round(time.time() - started, 1),
        "stale_after_hours": C.STALE_DATA_HOURS,
        "repo_url": C.GITHUB_REPO_URL,
        "site_url": C.SITE_URL,
    }
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")

    CACHE.mkdir(parents=True, exist_ok=True)
    REJECT_CACHE.write_text(json.dumps(rejected, ensure_ascii=False, indent=1), "utf-8")

    log(f"\nИТОГ: {len(published)} вакансий (без опыта: {meta['no_experience']}, "
        f"новых за 24ч: {new_today}, порог доверия: {trust_min})")
    log(f"Категории: {dict(cats)}")
    log(f"Отсев: {dict(reasons.most_common(10))}")
    log(f"Запросов: {client.requests_done}, время: {meta['duration_sec']}s, источник: {source}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Сборщик вакансий Кама.Работа")
    p.add_argument("--offline", action="store_true", help="пересобрать выдачу из кэша, без сети")
    p.add_argument("--no-details", action="store_true", help="не догружать описания")
    p.add_argument("--source", choices=("auto", "api", "html"), default="auto")
    p.add_argument("--pages", type=int, default=C.MAX_PAGES_PER_PASS)
    p.add_argument("--limit-details", type=int, default=C.MAX_DETAIL_FETCH)
    p.add_argument("--min-trust", type=int, default=None)
    args = p.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())