# -*- coding: utf-8 -*-
"""Фильтрация вакансий по ТЗ «Кама.Работа» (п. 4).

Всё, что решает «брать / не брать», живёт здесь; слова и пороги — в config.py.
Каждый отказ возвращается с причиной, чтобы прогон можно было проверить глазами.
"""
from __future__ import annotations

import html
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

import config as C

_WS = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")
_CYR = re.compile(r"[А-Яа-яЁёA-Za-z]")


def norm(text: str | None) -> str:
    """Нижний регистр, ё -> е, схлопнутые пробелы."""
    if not text:
        return ""
    return _WS.sub(" ", html.unescape(str(text)).replace("ё", "е").replace("Ё", "Е").lower()).strip()


def plain_text(raw_html: str | None) -> str:
    if not raw_html:
        return ""
    txt = re.sub(r"<\s*(br|/p|/li|/div|/h[1-6])\s*/?>", "\n", raw_html, flags=re.I)
    txt = _TAG.sub(" ", txt)
    txt = html.unescape(txt).replace("\xa0", " ")
    return _WS.sub(" ", txt).strip()


def haystack(v: dict, with_description: bool = True) -> str:
    parts = [v.get("title"), (v.get("employer") or {}).get("name")]
    if with_description:
        parts.append(v.get("description_text"))
        parts.append(" ".join(v.get("key_skills") or []))
    return norm(" ".join(p for p in parts if p))


def title_text(v: dict) -> str:
    return norm(v.get("title"))


# --- зарплата -------------------------------------------------------------

def monthly_from(v: dict) -> int | None:
    s = v.get("salary") or {}
    return s.get("from") or s.get("to")


def monthly_to(v: dict) -> int | None:
    s = v.get("salary") or {}
    return s.get("to") or s.get("from")


def salary_passes(v: dict) -> bool:
    """salary_from >= 50000, либо from не указан и to >= 50000."""
    s = v.get("salary") or {}
    if (s.get("currency") or C.CURRENCY) != C.CURRENCY:
        return False
    frm, to = s.get("from"), s.get("to")
    if frm is not None:
        return frm >= C.MIN_SALARY
    return to is not None and to >= C.MIN_SALARY


# --- жёсткие условия ------------------------------------------------------

def is_perm_city(city: str | None, district: str | None = None) -> bool:
    """Адрес рабочего места действительно в Пермском крае."""
    if norm(district) in C.PERM_DISTRICTS:
        return True
    name = norm(city)
    if not name:
        return True
    for pref in C.CITY_PREFIXES:
        if name.startswith(pref):
            name = name[len(pref):].strip()
            break
    if "перм" in name:
        return True
    return name in C.PERM_LOCALITIES or name.split()[0] in C.PERM_LOCALITIES


def hard_reject(v: dict, now: datetime | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    if v.get("archived"):
        return "архив"
    area = v.get("area") or {}
    is_remote = "remote" in (v.get("work_formats") or []) or v.get("schedule") == "remote"
    addr = v.get("address") or {}
    # hh иногда публикует пермскую вакансию под id соседнего региона,
    # но адрес рабочего места при этом пермский — доверяем адресу
    addr_is_perm = bool(norm(addr.get("city"))) and is_perm_city(addr.get("city"), addr.get("district"))
    if area.get("id") not in (None, C.AREA_ID) and C.AREA_NAME not in (area.get("name") or ""):
        if not (C.INCLUDE_REMOTE and is_remote) and not addr_is_perm:
            return "не Пермь"
    if not is_remote and not is_perm_city(addr.get("city"), addr.get("district")):
        return f"не Пермь: {addr.get('city')}"
    published = parse_dt(v.get("published_at"))
    if published is None:
        return "нет даты"
    age_days = (now - published).total_seconds() / 86400
    if age_days > C.MAX_AGE_DAYS:
        return f"старше {C.MAX_AGE_DAYS} дней"
    if age_days < -1:
        return "дата из будущего"
    if not salary_passes(v):
        return "зарплата ниже порога"
    if (monthly_from(v) or 0) > C.SALARY_MAX_PLAUSIBLE:
        return "нереальная зарплата"
    emp_type = str(v.get("employment") or "").lower().replace("_", "")
    allowed = {e.lower().replace("_", "") for e in C.ALLOWED_EMPLOYMENT}
    if emp_type and emp_type not in allowed:
        return "тип занятости"
    if not v.get("title"):
        return "без названия"
    return None


def parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    txt = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(txt[:19], fmt[:len(txt) + 2] if fmt == "%Y-%m-%d" else fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


# --- гео-обманки ----------------------------------------------------------

GEO_OTHER_CITIES = [
    "москва", "санкт-петербург", "петербург", "софьино", "елабуга", "владикавказ",
    "казань", "екатеринбург", "ижевск", "уфа", "челябинск", "тюмень", "сургут",
    "новый уренгой", "нижний новгород", "новосибирск", "краснодар", "ростов",
    "самара", "воронеж", "волгоград", "пермский край вахта", "набережные челны",
    "тольятти", "оренбург", "киров", "сыктывкар", "мурманск", "анапа", "сочи",
    "алабуга", "нахабино", "подольск", "домодедово", "раменское", "щулково",
    "янао", "ханты-мансийск", "муравленко", "ноябрьск", "салехард", "нефтеюганск",
    "нижневартовск", "когалым", "лангепас", "мегион", "сургутский", "березники вахта",
]


GEO_WORKPLACE_RE = re.compile("(?:" + "|".join(C.GEO_WORKPLACE_MARKERS) + r")\s*[:—-]?\s*([^.:;]{0,80})")


def geo_reject(v: dict) -> str | None:
    """Вакансия числится в Перми, а работать предлагают в другом городе."""
    if v.get("schedule") == "remote" or "remote" in (v.get("work_formats") or []):
        return None
    t = title_text(v)
    for city in GEO_OTHER_CITIES:
        if re.search(r"(?<![а-я])" + re.escape(city) + r"(?![а-я])", t):
            if "перм" in t:
                continue
            return f"другой город: {city}"
    if "перм" not in t:
        for stem in C.GEO_OTHER_STEMS:
            if len(stem) >= 4 and stem in t:
                return f"другой город: {stem}"
    desc = norm(v.get("description_text"))
    if not desc:
        return None
    for m in GEO_WORKPLACE_RE.finditer(desc):
        tail = m.group(1)
        if "перм" in tail:
            continue
        for stem in C.GEO_OTHER_STEMS:
            if stem in tail:
                return f"другой регион: {tail.strip()[:60]}"
    return None


# --- стоп-листы -----------------------------------------------------------

def gender_reject(v: dict) -> str | None:
    t = title_text(v)
    desc = norm(v.get("description_text"))
    for w in C.GENDER_STOP_WORDS:
        nw = norm(w)
        if nw and nw in t:
            return f"стоп-профессия: {w}"
    for pat in C.GENDER_REQUIREMENT_PATTERNS:
        if re.search(pat, t):
            return "требование к полу в названии"
        if desc and re.search(pat, desc):
            return "требование к полу в описании"
    for w in C.GENDER_STOP_WORDS:
        nw = norm(w)
        if nw and desc and nw in desc and not any(n in t for n in C.GENDER_NEUTRAL_WORDS):
            # в описании — только если это явно профиль работы, а не упоминание мимоходом
            if re.search(r"(?:работ|должност|обязанност|услуг|клиент)[^.]{0,60}" + re.escape(nw), desc):
                return f"стоп-профессия в описании: {w}"
    return None


def manual_review(v: dict) -> str | None:
    t = title_text(v)
    for pat in C.MANUAL_REVIEW_PATTERNS:
        if re.search(pat, t):
            return "проверить вручную"
    return None


def _is_all_caps(title: str) -> bool:
    letters = [ch for ch in title if ch.isalpha()]
    if len(letters) < C.ALL_CAPS_MIN_LEN:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    return upper / len(letters) >= C.ALL_CAPS_RATIO


def scam_reject(v: dict) -> str | None:
    t = title_text(v)
    raw_title = v.get("title") or ""
    text = haystack(v)
    for w in C.SCAM_STOP_WORDS:
        nw = norm(w)
        if not nw:
            continue
        if nw in text:
            where = "название" if nw in t else "описание"
            return f"скам-стоп ({where}): {w}"
    for pat in C.SCAM_TITLE_REGEX:
        if re.search(pat, raw_title):
            return "мусорное название"
    if _is_all_caps(raw_title):
        return "СПЛОШНОЙ КАПС"
    if re.search(C.DAILY_RATE_PATTERN, text) and v.get("experience") == "noExperience":
        if not re.search(r"обязанност|требовани|график работы|адрес", text):
            return "«от 5000 в день» без обязанностей"
    if v.get("employer", {}).get("anonymous"):
        return "работодатель без названия"
    return None


def soft_stop_hits(v: dict) -> list[str]:
    text = haystack(v)
    hits = [w for w in C.SOFT_STOP_WORDS if norm(w) in text]
    contacts = norm(v.get("contact_text"))
    if contacts and re.search(C.MESSENGER_ONLY_PATTERN, contacts):
        if not re.search(r"телефон|phone|\+7|e-mail|@", contacts):
            hits.append("связь только через мессенджер")
    return hits


def reject_reason(v: dict, now: datetime | None = None) -> str | None:
    for fn in (hard_reject, geo_reject, gender_reject, scam_reject, manual_review):
        reason = fn(v, now) if fn is hard_reject else fn(v)
        if reason:
            return reason
    return None


# --- категории, теги, сниппет ---------------------------------------------

def categorize(v: dict) -> tuple[str, list[str]]:
    t = haystack(v, with_description=False)
    scores: dict[str, int] = {}
    for cat in ("hands", "head", "service"):
        words = C.CATEGORIES[cat]["words"]
        hits = 0
        for w in words:
            nw = norm(w)
            if len(nw) <= 2:
                if re.search(r"(?<![а-яa-z])" + re.escape(nw) + r"(?![а-яa-z])", t):
                    hits += 1
            elif nw in t:
                hits += 2 if nw in title_text(v) else 1
        if hits:
            scores[cat] = hits
    primary = max(scores, key=lambda k: scores[k]) if scores else "other"
    extras = [primary]
    if v.get("schedule") == "remote" or "remote" in (v.get("work_formats") or []):
        extras.append("remote")
    if v.get("employment") in ("part", "project", "probation") or v.get("schedule") == "flexible" \
            or v.get("accept_temporary") or v.get("internship"):
        extras.append("part")
    seen, out = set(), []
    for c in extras:
        if c not in seen:
            seen.add(c)
            out.append(c)
    if primary == "other":
        out = [c for c in out if c != "other"] + ["other"]
    return primary, out


def make_tags(v: dict) -> list[str]:
    text = haystack(v)
    tags = []
    for tag, pat in C.TAG_PATTERNS.items():
        if re.search(pat, text):
            tags.append(tag)
    if v.get("experience") == "noExperience" and "без опыта" not in tags:
        tags.insert(0, "без опыта")
    freq = (v.get("salary") or {}).get("frequency")
    if freq == "DAILY":
        tags.append("ежедневные выплаты")
    elif freq == "WEEKLY":
        tags.append("еженедельные выплаты")
    days = v.get("schedule_days") or []
    for code, label in (("TWO_ON_TWO_OFF", "2/2"), ("THREE_ON_THREE_OFF", "3/3"),
                        ("FIVE_ON_TWO_OFF", "5/2"), ("SIX_ON_ONE_OFF", "6/1"),
                        ("TWO_ON_ONE_OFF", "2/1"), ("FOUR_ON_TWO_OFF", "4/2")):
        if code in days:
            tags.append(label)
            break
    out, seen = [], set()
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:6]


def make_snippet(v: dict) -> str:
    sn = v.get("snippet") or {}
    parts = [sn.get("responsibility"), sn.get("requirement")]
    text = " ".join(plain_text(p) for p in parts if p).strip()
    if not text:
        desc = v.get("description_text") or ""
        text = desc
    text = _WS.sub(" ", text).strip(" •-\n")
    if len(text) > C.SNIPPET_MAX_LEN:
        cut = text[:C.SNIPPET_MAX_LEN]
        sp = cut.rfind(" ")
        text = (cut[:sp] if sp > 80 else cut).rstrip(" ,;:.") + "…"
    return text


# --- дедупликация и клоны -------------------------------------------------

def dedupe(vacs: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for v in vacs:
        vid = str(v.get("id"))
        if not vid or vid == "None":
            continue
        prev = by_id.get(vid)
        if prev is None or len(v.get("description_text") or "") > len(prev.get("description_text") or ""):
            by_id[vid] = v
    seen_keys = set()
    out = []
    for v in by_id.values():
        s = v.get("salary") or {}
        key = (
            norm((v.get("employer") or {}).get("name")),
            title_text(v),
            norm((v.get("address") or {}).get("district")),
            s.get("from"), s.get("to"),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(v)
    return out


def _similar(a: dict, b: dict) -> bool:
    ta, tb = title_text(a), title_text(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    wa, wb = set(ta.split()), set(tb.split())
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.7


def collapse_employer(vacs: list[dict]) -> list[dict]:
    """10+ почти одинаковых вакансий одного работодателя -> одна свежая + «+N похожих»."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for v in vacs:
        groups[norm((v.get("employer") or {}).get("name")) or "?"].append(v)
    out = []
    for emp, items in groups.items():
        if len(items) < C.SAME_EMPLOYER_SIMILAR_LIMIT:
            out.extend(items)
            continue
        buckets: list[list[dict]] = []
        for v in sorted(items, key=lambda x: x.get("published_at") or "", reverse=True):
            for b in buckets:
                if _similar(v, b[0]):
                    b.append(v)
                    break
            else:
                buckets.append([v])
        for b in buckets:
            if len(b) >= C.SAME_EMPLOYER_SIMILAR_LIMIT:
                keep = dict(b[0])
                keep["similar_count"] = len(b) - 1
                keep["similar_employers"] = emp
                out.append(keep)
            else:
                out.extend(b)
    return out


def find_clones(vacs: list[dict]) -> set[str]:
    """Одинаковый текст у 5+ вакансий разных компаний."""
    by_text: dict[str, set[str]] = defaultdict(set)
    for v in vacs:
        txt = norm(v.get("description_text"))
        if len(txt) < 200:
            continue
        key = re.sub(r"[^а-яa-z0-9 ]", "", txt)[:600]
        by_text[key].add(str(v.get("id")))
    clones: set[str] = set()
    for key, ids in by_text.items():
        emps = {norm((v.get("employer") or {}).get("name")) for v in vacs if str(v.get("id")) in ids}
        if len(ids) >= C.CLONE_MIN_COUNT and len(emps) >= C.CLONE_MIN_COUNT:
            clones |= ids
    return clones


def employer_counts(vacs: list[dict]) -> Counter:
    return Counter(norm((v.get("employer") or {}).get("name")) for v in vacs)


def is_known_employer(v: dict, counts: Counter) -> bool:
    emp = v.get("employer") or {}
    if emp.get("category") not in (None, "COMPANY"):
        return False
    if not emp.get("name") or emp.get("anonymous"):
        return False
    if not (emp.get("id") or emp.get("url") or emp.get("site") or emp.get("logo")):
        return False
    name = norm(emp.get("name"))
    if counts.get(name, 0) >= 2:
        return True
    return any(m in name for m in C.KNOWN_EMPLOYER_MARKERS)


PERSON_NAME = re.compile(
    r"^[а-яё]+ [а-яё]+ (?:[а-яё]+ович|[а-яё]+евич|[а-яё]+овна|[а-яё]+евна|[а-яё]+ична|[а-яё]+инична)$"
)


def is_anonymous_employer(v: dict) -> bool:
    emp = v.get("employer") or {}
    if emp.get("category") in ("PRIVATE_INDIVIDUAL", "SELF_EMPLOYED", "PRIVATE_RECRUITER"):
        return True
    name = norm(emp.get("name"))
    if not name:
        return True
    if PERSON_NAME.match(name):
        return True
    return bool(re.search(r"^(ищу сотрудника|частное лицо|работодатель|не указано)", name))


SOCIAL_PACKAGE_PATTERN = (
    r"тк рф|трудов.{0,15}договор|официальн.{0,15}(оформлен|трудоустрой)|белая зарплат|"
    r"соцпакет|дмс|полис|оплачиваем.{0,12}(отпуск|больничн)|отпускные|больничн|"
    r"спецодежд|компенсац.{0,12}(питан|проезд|гсм)|медкнижк"
)


def has_social_package(v: dict) -> bool:
    return bool(re.search(SOCIAL_PACKAGE_PATTERN, haystack(v)))


def has_address(v: dict) -> bool:
    a = v.get("address") or {}
    return bool(a.get("street") or a.get("district") or a.get("metro") or a.get("display"))


def description_is_full(v: dict) -> bool:
    txt = norm(v.get("description_text"))
    if len(txt) < C.DESCRIPTION_FULL_LEN:
        return False
    return bool(re.search(r"обязанност|требовани|услови|что мы|задач|график|мы предлагаем", txt))


def age_days(v: dict, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    dt = parse_dt(v.get("published_at"))
    return (now - dt).total_seconds() / 86400 if dt else 99.0