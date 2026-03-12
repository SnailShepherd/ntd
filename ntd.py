#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NTD builder — рабочая, самодостаточная версия (cp1251, порядок фильтров, STRICT по классификаторам по умолчанию).

Что делает:
  • Читает входные HTML-таблицы (2 или 3 колонки):
      - 3 колонки: URL | Папки | Документ
      - 2 колонки: URL | Документ
  • Предфильтр по типам/исключениям; проверка «-2025» только для стандартов.
  • Маппинг «Папок» → классификаторы (classifiers_map.csv → classifiers.csv).
    ⚠ По умолчанию действует режим STRICT: если в таблице нет ни одного нужного классификатора,
      строка отбрасывается. STRICT включается автоматически, если файл classifiers.csv не пуст.
      Отключить можно флагом --loose-classifiers.
  • --dry выводит список карточек к скачиванию и общий счётчик.
  • В рабочем режиме качает карточки NormaCS с кэшем и собирает HTML-отчёт.

Примеры:
  python ntd_builder.py --input-dir data/tables --dry
  python ntd_builder.py --input-dir data/tables --dry --why
  python ntd_builder.py --input-dir data/tables --out out/ntd_20250819.html
  python ntd_builder.py --input-dir data/tables --dry --strict-classifiers
  python ntd_builder.py --input-dir data/tables --dry --loose-classifiers
"""

from __future__ import annotations
import argparse
import dataclasses
import html
import json
import re
import sys
import shutil
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

# ---------------------
# Константы и настройки
# ---------------------
ALLOWED_TYPES_GENERAL = {
    "ГОСТ", "ГОСТ Р", "ГОСТ ISO", "ГОСТ ИСО", "ГОСТ EN", "ГОСТ IEC", "ГОСТ МЭК",
    "ПНСТ", "СП", "Постановление", "Приказ", "Письмо", "Распоряжение", "Решение",
    "Федеральный закон", "ФЗ", "ФКЗ", "Кодекс", "ТР ТС", "ТР ЕАЭС", "РД", "ОСТ", "ФНП", "СанПиН"
}

EXCLUDED_PREFIXES = [
    "Указ ", "Указание ", "Типовой проект ", "Фармакопейная статья ", "Проект ",
    "Изменение ", "Серия ", "М ", "МР ", "МУК ", "Положение ",
    "Поручение ", "Извещение ", "Информация ", "Поправка ", "МИ ", "Инструкция ", "Соглашение "
]

EXCLUDED_REGEX_COMMON = re.compile(r"(?i)"
    r"(?:\bсредств\w*\s+измерен\w*\b)"  # СИ/метрология
    r"|(?:профессиональн\w*\s+стандарт\w*)"
    r"|(?:стандарт\w*\s+медицинск\w*\s+помощ\w*)"
    r"|(?:фармакопе\w*\s+стат\w*)"
    r"|(?:\bо\s+рассмотрени[ея]\s+обращен\w*)"
    r"|(?:\bросатом\b)"
    r"|(?:\bо\s+направлени\w*\s+информац\w*\b)"
)

EXCLUDED_REGEX_SPEC: Dict[str, str] = {
    "Приказ": r"(?i)(фармакопе\w*\s+стат\w*|стандарт\w*\s+медицинск\w*\s+помощ\w*|\bросатом\b)",
    "Письмо": r"(?i)\bо\s+рассмотрени[ея]\s+обращен\w*",
}

PRE_CHECK_YEAR_TYPES = {"ГОСТ", "ГОСТ Р", "ГОСТ ISO", "ГОСТ ИСО", "ГОСТ EN", "ГОСТ IEC", "ГОСТ МЭК", "ПНСТ", "СП"}

HIGH_VOLUME_ORGS_GENITIVE = {
    "Коллегия ЕЭК": "Коллегии ЕЭК",
    "Совет ЕЭК": "Совета ЕЭК",
    "Роструд": "Роструда",

    "Правительство РФ": "Правительства РФ",
    "Президент РФ": "Президента РФ",
    "Государственная Дума": "Государственной Думы",
    "Совет Федерации": "Совета Федерации",
    "Банк России": "Банка России",
    "Счетная палата России": "Счетной палаты России",
    "Генпрокуратура России": "Генпрокуратуры России",
    "Судебный департамент при Верховном Суде Российской Федерации": "Судебного департамента при Верховном Суде Российской Федерации",
    "Минфин России": "Минфина России",
    "Минэкономразвития России": "Минэкономразвития России",
    "Минтруд России": "Минтруда России",
    "Минздрав России": "Минздрава России",
    "Минпросвещения России": "Минпросвещения России",
    "Минобрнауки России": "Минобрнауки России",
    "Минпромторг России": "Минпромторга России",
    "Минкультуры России": "Минкультуры России",
    "Минэнерго России": "Минэнерго России",
    "Минтранс России": "Минтранса России",
    "Минприроды России": "Минприроды России",
    "МВД России": "МВД России",
    "МЧС России": "МЧС России",
    "Минстрой России": "Минстроя России",
    "Минсельхоз России": "Минсельхоза России",
    "Ростехнадзор": "Ростехнадзора",
    "Росстандарт": "Росстандарта",
    "Росздравнадзор": "Росздравнадзора",
    "Роспотребнадзор": "Роспотребнадзора",
    "Росприроднадзор": "Росприроднадзора",
    "Росрыболовство": "Росрыболовства",
    "Росавтодор": "Росавтодора",
    "Росалкогольрегулирование": "Росалкогольрегулирования",
    "Росморречфлот": "Росморречфлота",
    "Роскомнадзор": "Роскомнадзора",
    "Рослесхоз": "Рослесхоза",
    "Роснедра": "Роснедр",
    "Росводресурсы": "Росводресурсов",
    "Росимущество": "Росимущества",
    "Росгвардия": "Росгвардии",
    "Росстат": "Росстата",
    "ФНС России": "ФНС России",
    "ФТС России": "ФТС России",
    "ФАС России (Федеральная антимонопольная служба)": "ФАС России",
    "ФАС России": "ФАС России",
    "ФССП России": "ФССП России",
    "ФМС России": "ФМС России",
    "ФСБ России": "ФСБ России",
    "ФСТ России": "ФСТ России",
    "Росреестр": "Росреестра",
    "Росгидромет": "Росгидромета",
}

GENDER_BY_TYPE = {
    "ГОСТ": "опубликован", "ГОСТ Р": "опубликован", "ГОСТ ISO": "опубликован", "ГОСТ ИСО": "опубликован",
    "ГОСТ EN": "опубликован", "ГОСТ IEC": "опубликован", "ГОСТ МЭК": "опубликован",
    "СП": "опубликован", "Приказ": "опубликован", "Федеральный закон": "опубликован",
    "Кодекс": "опубликован", "ТР ТС": "опубликован", "ТР ЕАЭС": "опубликован",
    "РД": "опубликован", "ПНСТ": "опубликован", "ОСТ": "опубликован",
    "Постановление": "опубликовано", "Распоряжение": "опубликовано", "Решение": "опубликовано", "Письмо": "опубликовано",
    "ФНП": "опубликованы", "СанПиН": "опубликованы",
}

NO_COMMA_NUMBER_IN_TITLE = {"ГОСТ", "ГОСТ Р", "ГОСТ ISO", "ГОСТ ИСО", "ГОСТ EN", "ГОСТ IEC", "ГОСТ МЭК", "СП", "ПНСТ"}
SKIP_MINISTRY_AND_DATE_IN_TITLE = {"ГОСТ", "ГОСТ Р", "ГОСТ ISO", "ГОСТ ИСО", "ГОСТ EN", "ГОСТ IEC", "ГОСТ МЭК", "СП", "ПНСТ"}
FED_LAW_TYPES = {"Федеральный закон", "Федеральный конституционный закон", "ФКЗ"}


ORG_FILTER_ALLOWLIST: Set[str] = set()
ORG_FILTER_BLOCKLIST: Set[str] = {"ФГБУ \"ФЦАО\""}

HTTP_HEADERS = {
    "User-Agent": "NTD builder (normacs helper) / 1.5",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# -------------------------
# Вспомогательные структуры
# -------------------------
@dataclasses.dataclass
class TableRow:
    url: str
    folders_html: str
    document_title: str
    src_file: Path

@dataclasses.dataclass
class CardInfo:
    doc_id: str
    url: str
    type_str: str
    number: str
    designation: str
    name: str
    status: Optional[str]
    synonyms: Optional[str]
    approved_raw: Optional[str]
    approved_short: Optional[str]
    approved_date: Optional[str]
    classifiers: List[str]

# -----------------
# Утилиты и парсеры
# -----------------

def clean_url(u: str) -> str:
    parts = urlsplit(u.strip())
    q = []
    for k, v in parse_qsl(parts.query, keep_blank_values=False):
        if k.lower().startswith("utm_"):
            continue
        if k.lower() in {"gclid", "fbclid", "yclid", "from", "ref"}:
            continue
        if v == "":
            continue
        q.append((k, v))
    query = urlencode(q, doseq=True)
    scheme = (parts.scheme or "http").lower()
    netloc = parts.netloc.lower()
    path = re.sub(r"/{2,}", "/", parts.path)
    return urlunsplit((scheme, netloc, path, query, ""))


def extract_id_from_url(u: str) -> Optional[str]:
    m = re.search(r"/doc/([A-Za-z0-9]+)\.html(?:$|\?)", u, re.IGNORECASE)
    return m.group(1) if m else None


def detect_type_from_cell_title(s: str) -> Optional[str]:
    text = s.strip()
    if not text:
        return None
    head = text.split(".", 1)[0].strip()
    head_tokens = head.split()
    multiword = [
        "Федеральный закон", "ГОСТ Р", "ГОСТ ISO", "ГОСТ ИСО", "ГОСТ EN", "ГОСТ IEC", "ГОСТ МЭК", "ТР ТС", "ТР ЕАЭС",
    ]
    for mw in multiword:
        if head.startswith(mw + " "):
            return mw
    if not head_tokens:
        return None
    first = head_tokens[0]
    if first in {"ГОСТ", "СП", "Постановление", "Приказ", "Письмо", "Распоряжение", "Решение",
                 "ФКЗ", "Кодекс", "РД", "ОСТ", "ПНСТ", "ФНП", "СанПиН"}:
        return first if first != "ФКЗ" else "ФКЗ"
    if re.match(r"^ФЗ\b", head):
        return "Федеральный закон"
    return None


def is_excluded_by_prefix(doc_title: str) -> bool:
    t = doc_title.lstrip()
    return any(t.startswith(pref) for pref in EXCLUDED_PREFIXES)


def is_excluded_by_regex_common(s: str) -> bool:
    return bool(EXCLUDED_REGEX_COMMON.search(s))


def is_excluded_by_regex_spec(doc_type: Optional[str], s: str) -> bool:
    if not doc_type:
        return False
    pattern = EXCLUDED_REGEX_SPEC.get(doc_type)
    if not pattern:
        return False
    return bool(re.search(pattern, s, flags=re.IGNORECASE))


def parse_iso_date(s: str) -> Optional[date]:
    """Парсим дату из строк: YYYY-MM-DD | DD.MM.YYYY | YYYYMMDD."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_years_csv(s: str) -> Set[int]:
    years: Set[int] = set()
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        if re.fullmatch(r"\d{4}", part):
            years.add(int(part))
    return years


def parse_file_date_from_name(p: Path) -> Optional[date]:
    """Берём дату из имени файла YYYYMMDD*.html (если есть)."""
    m = re.match(r"^(\d{8})", p.stem)
    if not m:
        return None
    return parse_iso_date(m.group(1))


def extract_designation_year_from_title(doc_type: Optional[str], title: str) -> Optional[int]:
    """Для стандартов вытаскиваем год из обозначения прямо из заголовка таблицы."""
    if not doc_type:
        return None
    t = (title or "").strip()
    if doc_type == "СП":
        # СП 123.1325800.2025 ...
        m = re.match(r"^СП\s+[0-9][0-9\.]*\.(\d{4})\b", t)
        return int(m.group(1)) if m else None
    if doc_type in PRE_CHECK_YEAR_TYPES:
        # ГОСТ ...-2025 / ПНСТ ...-2026
        m = re.search(r"[\-–—]\s*(\d{4})\b", t)
        return int(m.group(1)) if m else None
    return None


def extract_designation_year_from_number(type_str: str, number: str) -> Optional[int]:
    """Год из номера, когда карточка уже скачана: ГОСТ ...-2025; СП ... .2025"""
    t = (type_str or "").strip()
    n = (number or "").strip()
    if not t or not n:
        return None
    if t == "СП":
        m = re.search(r"\.(\d{4})\b", n)
    else:
        m = re.search(r"[\-–—]\s*(\d{4})\b", n)
    return int(m.group(1)) if m else None


def is_allowed_standard_year(doc_type: Optional[str], title: str, allowed_years: Set[int]) -> bool:
    """Предфильтр: оставляем только стандарты с годом из allowed_years (если список задан)."""
    if doc_type not in PRE_CHECK_YEAR_TYPES:
        return True
    yr = extract_designation_year_from_title(doc_type, title)
    if yr is None:
        return False
    return (not allowed_years) or (yr in allowed_years)


# -------
# csv I/O
# -------

def _read_rows_any_delim(p: Path) -> List[List[str]]:
    import csv
    try:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError:
        return []
    for delim in (",", ";", "\t", "|"):
        rows = [r for r in csv.reader(text.splitlines(), delimiter=delim)]
        if len(rows) >= 1 and sum(1 for r in rows if len(r) >= 1) / max(1, len(rows)) >= 0.8:
            return rows
    return [line.split(",") for line in text.splitlines()]


def load_classifiers(klass_path: Path) -> Set[str]:
    rows = _read_rows_any_delim(klass_path)
    if not rows:
        return set()
    header = [c.strip().lower() for c in rows[0]]
    labels: Set[str] = set()
    if "label" in header:
        idx = header.index("label"); data = rows[1:]
    else:
        idx = 0; data = rows
    for r in data:
        if idx < len(r):
            lab = (r[idx] or "").strip()
            if lab:
                labels.add(lab)
    return labels


def load_classifiers_map(map_path: Path) -> List[Tuple[re.Pattern, str]]:
    rows = _read_rows_any_delim(map_path)
    if not rows:
        return []
    header = [c.strip().lower() for c in rows[0]]
    def _col(name_opts: List[str]) -> Optional[int]:
        for name in name_opts:
            if name in header:
                return header.index(name)
        return None
    p_idx = _col(["pattern"])
    c_idx = _col(["canonical_label", "canonical"])
    start = 1 if p_idx is not None and c_idx is not None else 0
    if p_idx is None or c_idx is None:
        p_idx, c_idx, start = 0, 1, 0
    rules: List[Tuple[re.Pattern, str]] = []
    for r in rows[start:]:
        if max(p_idx, c_idx) >= len(r):
            continue
        patt = (r[p_idx] or "").strip()
        canon = (r[c_idx] or "").strip()
        if not patt or not canon:
            continue
        try:
            rules.append((re.compile(patt, re.IGNORECASE), canon))
        except re.error as e:
            print(f"[WARN] Некорректный pattern в classifiers_map: {patt} ({e})", file=sys.stderr)
    return rules


def _sniff_encoding_from_meta(raw: bytes) -> Optional[str]:
    m = re.search(br"charset\s*=\s*([A-Za-z0-9_\-]+)", raw[:4096], flags=re.I)
    if m:
        try:
            return m.group(1).decode("ascii", errors="ignore").lower()
        except Exception:
            return None
    return None


def read_html_best_effort(file_path: Path) -> str:
    raw = file_path.read_bytes()
    enc = _sniff_encoding_from_meta(raw)
    tried: List[str] = []
    for enc_try in ([enc] if enc else []) + ["utf-8", "cp1251", "windows-1251"]:
        if not enc_try or enc_try in tried:
            continue
        tried.append(enc_try)
        try:
            return raw.decode(enc_try)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_folder_tokens(folders_html: str) -> List[str]:
    """Достаём метки из колонки «Папки». Разделители: '/', ';', ',', '•', '·', '|', '>'."""
    txt = BeautifulSoup(folders_html or "", "html.parser").get_text(" / ")
    txt = re.sub(r"[ \u00A0]+", " ", txt).strip()
    parts = re.split(r"[\/;\,\|\u2022\u00B7>]+", txt)
    return [p.strip() for p in parts if p.strip()]


def map_classifiers(tokens: List[str], rules: List[Tuple[re.Pattern, str]], allowed: Set[str]) -> List[str]:
    """Сопоставляем токены папок с каноническими метками. Если allowed пуст — не фильтруем по белому списку."""
    seen = set(); result = []
    allow_check = bool(allowed)
    for t in tokens:
        t_norm = t.strip()
        if (not allow_check or t_norm in allowed) and t_norm not in seen and t_norm:
            seen.add(t_norm); result.append(t_norm); continue
        for patt, canon in rules:
            if patt.search(t_norm):
                if (not allow_check or canon in allowed) and canon not in seen:
                    seen.add(canon); result.append(canon)
                break
    return result


def fetch_with_cache(url: str, cache_path: Path, sleep_sec: float, timeout: float = 20.0) -> Optional[str]:
    if cache_path.exists():
        try:
            return cache_path.read_text(encoding="cp1251", errors="replace")
        except Exception:
            pass
    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
        if resp.status_code == 200 and resp.content:
            text = resp.content.decode("cp1251", errors="replace")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(text, encoding="cp1251", errors="replace")
            time.sleep(max(0.0, sleep_sec))
            return text
        else:
            print(f"[WARN] HTTP {resp.status_code} {url}", file=sys.stderr)
    except requests.RequestException as e:
        print(f"[WARN] Ошибка загрузки {url}: {e}", file=sys.stderr)
    return None


def parse_card(html_text: str, url: str, classifiers: List[str]) -> Optional[CardInfo]:
    soup = BeautifulSoup(html_text, "html.parser")

    def find_field(label: str) -> Optional[str]:
        b = soup.find("b", string=re.compile(rf"^{re.escape(label)}\s*$|(?:повероч\w*\s+схем\w*)", re.IGNORECASE))
        if not b:
            return None
        accum = []
        for el in b.next_siblings:
            if getattr(el, "name", None) == "br":
                break
            accum.append(el.get_text(strip=False) if hasattr(el, "get_text") else str(el))
        val = "".join(accum)
        val = re.sub(r"\s+", " ", html.unescape(val)).strip()
        return val or None

    designation = find_field("Обозначение:")
    name = find_field("Наименование:")
    status = find_field("Статус:")
    synonyms = find_field("Синонимы:")
    approved = find_field("Утвержден:")

    if not designation:
        return None

    m = re.match(r"^\s*([А-ЯA-ZЁ][^0-9,;]*)\s+([0-9A-Za-z\-/\.]+)\s*$", designation)
    if not m:
        m = re.match(r"^\s*([А-ЯA-ZЁ][^0-9,;]*)\s+(.*)$", designation)
    if not m:
        return None

    type_str = m.group(1).strip()
    number = m.group(2).strip() if m.lastindex and m.lastindex >= 2 else ""

    approved_short = None; approved_date = None
    if approved:
        m1 = re.match(r"^\s*([^;]+)\s*;\s*.*?,\s*(\d{2}\.\d{2}\.\d{4})\s*$", approved)
        if m1:
            approved_short, approved_date = m1.group(1).strip(), m1.group(2).strip()
        else:
            m2 = re.match(r"^\s*([^,;]+).*,\s*(\d{2}\.\d{2}\.\d{4})\s*$", approved)
            if m2:
                approved_short, approved_date = m2.group(1).strip(), m2.group(2).strip()
            else:
                m3 = re.match(r"^\s*([^,;]+)\s*$", approved)
                if m3:
                    approved_short = m3.group(1).strip()

    doc_id = extract_id_from_url(url) or ""

    return CardInfo(
        doc_id=doc_id,
        url=url,
        type_str=type_str,
        number=number,
        designation=designation,
        name=name or "",
        status=status,
        synonyms=synonyms,
        approved_raw=approved,
        approved_short=approved_short,
        approved_date=approved_date,
        classifiers=classifiers,
    )



def to_genitive(short_name: Optional[str]) -> Optional[str]:
    if not short_name:
        return None
    n = short_name.strip()
    low = n.lower()
    # Жёсткие соответствия длинных официальных названий → короткие формы
    LONG2SHORT = {
        "министерство строительства и жилищно-коммунального хозяйства российской федерации": "Минстрой России",
        "министерство сельского хозяйства российской федерации": "Минсельхоз России",
        "федеральная служба государственной регистрации, кадастра и картографии": "Росреестр",
        "федеральная служба по гидрометеорологии и мониторингу окружающей среды": "Росгидромет",
        "федеральное агентство по техническому регулированию и метрологии": "Росстандарт",
        "евразийская экономическая комиссия": "ЕЭК",
        "евразийской экономической комиссии": "ЕЭК",
    }
    for k, v in LONG2SHORT.items():
        if k in low:
            canon = v
            break
    else:
        # Эвристики
        if ("строительст" in low and "жилищно" in low) and "министр" in low:
            canon = "Минстрой России"
        elif ("государственной регистрации" in low and "кадастр" in low and "картограф" in low) or "росреестр" in low:
            canon = "Росреестр"
        elif "гидрометеоролог" in low or "росгидромет" in low:
            canon = "Росгидромет"
        elif ("техническому регулированию" in low and "метролог" in low) or "росстандарт" in low:
            canon = "Росстандарт"
        elif "евразийск" in low and "экономическ" in low and "комисс" in low:
            if "коллег" in low:
                canon = "Коллегия ЕЭК"
            elif "совет" in low:
                canon = "Совет ЕЭК"
            else:
                canon = "ЕЭК"
        else:
            canon = n
    # Склонение по словарю; если нет — возвращаем канон
    return HIGH_VOLUME_ORGS_GENITIVE.get(canon, canon)



def published_word_for(card: CardInfo) -> str:
    # Любой ГОСТ — муж. род
    if re.match(r"^ГОСТ(\s|$)", card.type_str or "", re.IGNORECASE):
        return "опубликован"
    if re.match(r"^\s*Правила\b", card.name or "", re.IGNORECASE):
        return "опубликованы"
    return GENDER_BY_TYPE.get(card.type_str, "опубликовано")


def build_title(card: CardInfo) -> str:
    pw = published_word_for(card)
    is_gost_family = bool(re.match(r"^ГОСТ(\s|$)", card.type_str, re.IGNORECASE))
    is_fed_law = card.type_str in FED_LAW_TYPES
    # В первой строке:
    # - аббревиатуры и ГОСТ — как есть
    # - федеральные законы — с заглавной ("Федеральный закон"), без приведения к нижнему регистру
    # - остальное — со строчной
    ACRONYM_TYPES = {"СП", "ПНСТ", "ТР ТС", "ТР ЕАЭС", "РД", "ОСТ", "ФНП", "СанПиН"}
    if is_gost_family or is_fed_law or card.type_str in ACRONYM_TYPES:
        display_type = card.type_str
    else:
        display_type = card.type_str.lower()

    parts = [f"В NormaCS {pw} {display_type}"]

    # Ведомство/орган + дата:
    # - ГОСТ и группы из SKIP_MINISTRY_AND_DATE_IN_TITLE: не добавляем ни ведомство, ни дату
    # - Федеральные законы: ведомство не показываем, дату показываем
    skip_min_date = is_gost_family or card.type_str in SKIP_MINISTRY_AND_DATE_IN_TITLE
    if not skip_min_date:
        if (not is_fed_law):
            gen = to_genitive(card.approved_short)
            if gen:
                parts.append(gen)
        if card.approved_date:
            parts.append(f"от {card.approved_date}")

    # Для ГОСТ не ставим запятую перед номером

    no_comma_before_no = is_gost_family or card.type_str in NO_COMMA_NUMBER_IN_TITLE
    if no_comma_before_no:
        parts.append(card.number)
    else:
        parts.append(f", № {card.number}")

    title = " ".join([p for p in parts if p]).replace(" ,", ",").strip()
    if no_comma_before_no:
        title = title.replace(", №", "")
    return title



def build_content_block(card: CardInfo) -> str:
    pw = published_word_for(card)
    link_text = card.type_str + " " + card.number
    type_number_link = f'<a href="{html.escape(card.url)}" target="_blank" rel="noopener">{html.escape(link_text)}</a>'
    # Всегда добавляем наименование документа, даже для ГОСТов; без точки в конце
    first_line = f'В NormaCS {pw} {type_number_link} {html.escape(card.name)}'
    lines = [first_line]

    # Нормализация "Статуса": срезаем любые хвостовые DD.MM.YYYY, если они "прилипли" без пробела
    def _fix_status(s: str) -> str:
        if not s:
            return s
        import re as _re
        out = s
        while _re.search(r'(?<!\s)\d{2}\.\d{2}\.\d{4}$', out):
            out = _re.sub(r'(?<!\s)\d{2}\.\d{2}\.\d{4}$', '', out).rstrip()
        return out

    if card.status:
        st_low = card.status.lower()
        if not ("коммерчес" in st_low and "верс" in st_low):
            fixed = _fix_status(card.status)
            lines.append(f"<b>Статус:</b> {html.escape(fixed)}")
    if card.synonyms:
        lines.append(f"<b>Синонимы:</b> {html.escape(card.synonyms)}")
    if card.approved_raw:
        lines.append(f"<b>Утвержден:</b> {html.escape(card.approved_raw)}")
    paras = "".join(f"<p>{line}</p>" for line in lines)
    return paras



def render_summary_html(cards: List[CardInfo]) -> str:
    chunks = ['<!DOCTYPE html><html><head><meta charset="utf-8"><title>NTD summary</title></head><body>']
    for c in cards:
        title = html.escape(build_title(c))
        classifiers_html = "".join(f"<li>{html.escape(lbl)}</li>" for lbl in c.classifiers) or "<li>—</li>"
        content_html = build_content_block(c)
        chunks.append(f"""
<section>
  <h3>{title}</h3>
  <p><b>Идентификатор в NormaCS:</b> {html.escape(c.doc_id)}</p>
  <p><b>Ссылка на карточку:</b> {html.escape(c.url)}</p>
  <p><b>Классификаторы:</b></p>
  <ul>
    {classifiers_html}
  </ul>
  <p><b>Содержимое:</b></p>
  {content_html}
</section>
<hr/>
""")
    chunks.append("</body></html>")
    return "\n".join(chunks)

# -------------
# Основной ход
# -------------

def iter_table_rows(file_path: Path) -> Iterable[TableRow]:
    html_text = read_html_best_effort(file_path)
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table")
    if not table:
        return
    rows = table.find_all("tr")
    for tr in rows[1:]:  # пропускаем заголовок
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        # 1-я колонка — URL (может быть <a> или просто текст)
        a0 = tds[0].find("a")
        href = (a0.get("href", "").strip() if a0 else tds[0].get_text(strip=True))
        if href.startswith("/"):
            href = "https://www.normacs.ru" + href
        url_cell = href
        if len(tds) >= 3:
            folders_cell_html = str(tds[1])
            doc_td = tds[2]
        else:
            folders_cell_html = ""
            doc_td = tds[1]
        doc_cell = doc_td.get_text(" ", strip=True)
        if not doc_cell or doc_cell.startswith("."):
            continue
        yield TableRow(url=url_cell, folders_html=folders_cell_html, document_title=doc_cell, src_file=file_path)




def _ensure_unique_path(dst: Path) -> Path:
    """Если файл назначения уже есть — подбираем уникальное имя (name_1, name_2, ...)."""
    if not dst.exists():
        return dst
    stem, suffix = dst.stem, dst.suffix
    for i in range(1, 10000):
        cand = dst.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return cand
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return dst.with_name(f"{stem}_{ts}{suffix}")


def move_processed_tables(table_files: List[Path], done_dir: Path) -> int:
    """Перекладывает обработанные входные таблицы в done_dir. Возвращает число перемещённых файлов."""
    done_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for p in table_files:
        try:
            if not p.exists():
                continue
            target = _ensure_unique_path(done_dir / p.name)
            # shutil.move надёжнее Path.rename (в т.ч. при разных файловых системах)
            shutil.move(str(p), str(target))
            moved += 1
        except Exception as e:
            print(f"[WARN] Не удалось переместить {p} -> {done_dir}: {e}", file=sys.stderr)
    return moved


def main():
    ap = argparse.ArgumentParser(description="Сборщик новостных карточек NormaCS из HTML-таблиц с обновлениями.")
    ap.add_argument("--input-dir", required=True, help="Папка с HTML-таблицами (YYYYMMDD*.html)")
    ap.add_argument("--from-date", default="2025-09-01", help="Минимальная дата входных таблиц (YYYY-MM-DD | DD.MM.YYYY | YYYYMMDD). Фильтрация по имени файла YYYYMMDD*.html")
    ap.add_argument("--years", default="2025,2026", help="Допустимые годы документов (через запятую). Для стандартов год берётся из обозначения, для остальных — из даты утверждения")
    ap.add_argument("--out", default=None, help="Путь к итоговому HTML-отчёту")
    ap.add_argument("--cache-dir", default=".temp/cards", help="Директория кэша карточек")
    ap.add_argument("--done-dir", default=None, help="Куда перекладывать обработанные таблицы; по умолчанию sibling-папка 'done' рядом с input-dir")
    ap.add_argument("--no-move-done", action="store_true", help="Не переносить HTML-таблицы из input-dir в done-dir по завершении")
    ap.add_argument("--sleep", type=float, default=0.7, help="Пауза между запросами (сек)")
    ap.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout (сек)")
    ap.add_argument("--max", type=int, default=None, help="Ограничить число скачиваний за прогон")
    ap.add_argument("--dry", action="store_true", help="Сухой прогон: показать, что будем скачивать")
    ap.add_argument("--only-types", default=None, help="Список типов через запятую (напр. 'Постановление,СП')")
    ap.add_argument("--classifiers-csv", default="classifiers.csv", help="Путь к classifiers.csv (белый список)")
    ap.add_argument("--classifiers-map", default="classifiers_map.csv", help="Путь к classifiers_map.csv (регэкспы)")
    ap.add_argument("--excludes-json", default=None, help="JSON с доп. EXCLUDED_REGEX_SPEC {'Тип':'regex',...}")
    ap.add_argument("--strict-classifiers", action="store_true", help="Принудительно строгий режим по классификаторам")
    ap.add_argument("--loose-classifiers", action="store_true", help="Не отбрасывать строки без классификаторов даже при непустом classifiers.csv")
    ap.add_argument("--why", action="store_true", help="Пояснять, почему строка отброшена (в stdout)")
    args = ap.parse_args()

    min_date = parse_iso_date(args.from_date)
    allowed_years = parse_years_csv(args.years)

    input_dir = Path(args.input_dir)
    done_dir = Path(args.done_dir) if args.done_dir else (input_dir.parent / "done")
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    allowed_labels = load_classifiers(Path(args.classifiers_csv))
    rules = load_classifiers_map(Path(args.classifiers_map))

    if args.excludes_json:
        try:
            with open(args.excludes_json, "r", encoding="utf-8") as f:
                extra = json.load(f)
            for k, v in extra.items():
                EXCLUDED_REGEX_SPEC[k] = v
        except Exception as e:
            print(f"[WARN] Не удалось загрузить {args.excludes_json}: {e}", file=sys.stderr)

    only_types_set: Optional[Set[str]] = None
    if args.only_types:
        only_types_set = {t.strip() for t in args.only_types.split(",") if t.strip()}

    table_files = sorted([p for p in input_dir.glob("*.html") if p.is_file()])
    if min_date:
        filtered: List[Path] = []
        for p in table_files:
            fd = parse_file_date_from_name(p)
            if fd and fd < min_date:
                continue
            filtered.append(p)
        table_files = filtered

    if not table_files:
        print(f"[ERR] В {input_dir} не найдены *.html", file=sys.stderr)
        sys.exit(2)

    strict_mode = (args.strict_classifiers or bool(allowed_labels)) and not args.loose_classifiers
    if args.why:
        print(f"[DBG] allowed_labels={len(allowed_labels)}, rules={len(rules)}, STRICT={strict_mode}")

    selected_rows: List[Tuple[TableRow, List[str], str]] = []

    def why(reason: str, row: Optional[TableRow] = None):
        if args.why:
            src = f" [{row.src_file.name}]" if row else ""
            title = f" — {row.document_title}" if row else ""
            print(f"[WHY]{src}{title}: {reason}")

    # 1) Предфильтр строк таблиц
    for f in table_files:
        for row in iter_table_rows(f):
            url = clean_url(row.url)
            if not url:
                why("пустой URL", row); continue
            # Сначала распознаём тип
            doc_type = detect_type_from_cell_title(row.document_title)
            if not doc_type:
                if is_excluded_by_prefix(row.document_title):
                    why("исключён по префиксу", row)
                else:
                    why("тип не распознан", row)
                continue
            if is_excluded_by_regex_common(row.document_title):
                why("исключён по тематике (общий список)", row); continue
            if only_types_set and doc_type not in only_types_set:
                why("тип вне only-types", row); continue
            
            tokens = extract_folder_tokens(row.folders_html)
            mapped = map_classifiers(tokens, rules, allowed_labels)
            if strict_mode and not mapped:
                why("нет нужных классификаторов (STRICT)", row); continue
            # Дополняем отображаемые метки «разделами» из ПромЭксперта (например, "РАЗДЕЛ I. ...")
            extra_sections = [t for t in tokens if re.match(r"^\s*РАЗДЕЛ\s+[IVX]+\.", t, flags=re.IGNORECASE)]
            display_classifiers = []
            def _canon_label(lbl: str) -> str:
                if re.match(r"^\s*раздел\s*i\b", lbl, flags=re.IGNORECASE):
                    return "РАЗДЕЛ I. ТЕХНИЧЕСКОЕ РЕГУЛИРОВАНИЕ"
                return lbl
            for t in (extra_sections + mapped):
                t = _canon_label(t)
                if t and t not in display_classifiers:
                    display_classifiers.append(t)

            if not is_allowed_standard_year(doc_type, row.document_title, allowed_years):
                why("стандарт/СП вне разрешённых годов (обозначение)", row); continue
            selected_rows.append((dataclasses.replace(row, url=url), display_classifiers, doc_type))

    # 2) Скачивание карточек / dry-run
    to_download = selected_rows
    if args.max is not None:
        to_download = to_download[: args.max]

    cards: List[CardInfo] = []
    for row, mapped_classifiers, doc_type in to_download:
        doc_id = extract_id_from_url(row.url)
        if not doc_id:
            why("не удалось извлечь doc_id", row); continue
        cache_path = cache_dir / f"{doc_id.lower()}.html"

        if args.dry:
            print(f"[DRY] {doc_id} — {row.document_title}")
            continue

        html_text = fetch_with_cache(row.url, cache_path, sleep_sec=args.sleep, timeout=args.timeout)
        if not html_text:
            why("не удалось получить HTML карточки", row); continue

        if is_excluded_by_regex_spec(doc_type, html_text):
            why("исключён по тематике (тип-специфично)", row); continue

        card = parse_card(html_text, row.url, classifiers=mapped_classifiers)
        if not card:
            why("не распарсилась карточка", row); continue

        if ORG_FILTER_ALLOWLIST and (card.approved_short or "") not in ORG_FILTER_ALLOWLIST:
            why("не в allowlist организаций", row); continue
        if ORG_FILTER_BLOCKLIST and (card.approved_short or "") in ORG_FILTER_BLOCKLIST:
            why("в blocklist организаций", row); continue

        # Финальная проверка года документа (для стандартов/СП — по обозначению, для остальных — по дате утверждения)
        doc_year: Optional[int] = None
        if card.type_str in PRE_CHECK_YEAR_TYPES:
            doc_year = (
                extract_designation_year_from_number(card.type_str, card.number)
                or extract_designation_year_from_title(card.type_str, card.designation)
            )
        else:
            if card.approved_date:
                m_y = re.search(r"(\d{4})$", card.approved_date)
                if m_y:
                    doc_year = int(m_y.group(1))

        if doc_year is None:
            fd = parse_file_date_from_name(row.src_file)
            if fd:
                doc_year = fd.year

        if allowed_years and (doc_year is None or doc_year not in allowed_years):
            why(f"год документа вне разрешённых: {doc_year}", row); continue

        cards.append(card)

    if args.dry:
        print(f"[DRY] Всего к скачиванию: {len(to_download)}")
        return

    html_out = render_summary_html(cards)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(html_out, encoding="utf-8")
        print(f"[OK] Сводный HTML сохранён: {args.out} (карточек: {len(cards)})")
    else:
        sys.stdout.write(html_out)


    # Автоматически перекладываем обработанные входные таблицы в done_dir,
    # чтобы папка input-dir оставалась «чистой» для следующей выгрузки.
    if (not args.no_move_done) and (not args.dry):
        moved = move_processed_tables(table_files, done_dir)
        # Важно: не мусорим в stdout, если HTML выводился в stdout
        print(f"[OK] Перемещено таблиц в done: {moved} → {done_dir}", file=sys.stderr)



if __name__ == "__main__":
    main()
