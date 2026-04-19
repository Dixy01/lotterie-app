
from __future__ import annotations

import math
import re
import random
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Dict, Tuple, Optional

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
ARCHIVE_URL = "https://www.superenalotto.com/risultati/{year}"
LOTTO_NEWS_URL = "https://www.lotto-italia.it/news"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

MONTHS_IT = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

RUOTE = [
    "Bari", "Cagliari", "Firenze", "Genova", "Milano",
    "Napoli", "Palermo", "Roma", "Torino", "Venezia", "Nazionale"
]

# -------------------------------------------------
# DATACLASS
# -------------------------------------------------
@dataclass
class Draw:
    draw_date: date
    year: int
    main_numbers: List[int]
    jolly: Optional[int] = None
    superstar: Optional[int] = None


@dataclass
class LottoDraw:
    draw_date: date
    ruota: str
    numeri: List[int]


# -------------------------------------------------
# HTTP
# -------------------------------------------------
def http_get(url: str) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


# -------------------------------------------------
# SUPERENALOTTO (dal tuo file)
# -------------------------------------------------
def parse_italian_date(text: str) -> date:
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"(\d{1,2})\s+([a-zàéìòù]+)\s+(\d{4})", text)
    if not m:
        raise ValueError(f"Data non riconosciuta: {text}")
    day = int(m.group(1))
    month_name = m.group(2)
    year = int(m.group(3))
    if month_name not in MONTHS_IT:
        raise ValueError(f"Mese non riconosciuto: {month_name}")
    return date(year, MONTHS_IT[month_name], day)


def try_read_tables(html: str, year: int) -> List[Draw]:
    draws: List[Draw] = []
    try:
        tables = pd.read_html(html)
    except Exception:
        return draws

    for table in tables:
        cols = [str(c).lower() for c in table.columns]
        joined = " ".join(cols)
        if "data estrazione" not in joined and "risultato" not in joined and "numeri estratti" not in joined:
            continue

        date_col = None
        result_col = None
        for c in table.columns:
            low = str(c).lower()
            if "data" in low:
                date_col = c
            if "risultat" in low or "numeri" in low:
                result_col = c

        if date_col is None or result_col is None:
            continue

        for _, row in table.iterrows():
            date_text = str(row[date_col])
            result_text = str(row[result_col])
            nums = [int(n) for n in re.findall(r"\b\d{1,2}\b", result_text)]
            if len(nums) < 7:
                continue
            try:
                d = parse_italian_date(date_text)
            except Exception:
                continue

            main = nums[:6]
            jolly = nums[6] if len(nums) >= 7 else None
            superstar = nums[7] if len(nums) >= 8 else None
            draws.append(Draw(draw_date=d, year=year, main_numbers=main, jolly=jolly, superstar=superstar))

    return dedupe_draws(draws)


def parse_from_text(html: str, year: int) -> List[Draw]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\xa0", " ", text)
    text = re.sub(r"\n+", "\n", text)

    pattern = re.compile(
        r"(?P<date>\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4})\s+(?P<numbers>(?:\d{1,2}\s+){6,8})"
    )

    draws: List[Draw] = []
    for m in pattern.finditer(text):
        date_text = m.group("date")
        try:
            d = parse_italian_date(date_text)
        except Exception:
            continue
        if d.year != year:
            continue
        nums = [int(n) for n in re.findall(r"\b\d{1,2}\b", m.group("numbers"))]
        if len(nums) < 7:
            continue
        main = nums[:6]
        jolly = nums[6] if len(nums) >= 7 else None
        superstar = nums[7] if len(nums) >= 8 else None
        draws.append(Draw(draw_date=d, year=year, main_numbers=main, jolly=jolly, superstar=superstar))

    return dedupe_draws(draws)


def dedupe_draws(draws: List[Draw]) -> List[Draw]:
    seen = set()
    out: List[Draw] = []
    for draw in sorted(draws, key=lambda x: x.draw_date):
        key = (draw.draw_date, tuple(draw.main_numbers), draw.jolly, draw.superstar)
        if key not in seen:
            seen.add(key)
            out.append(draw)
    return out


@st.cache_data(show_spinner=False)
def fetch_super_draws(start_year: int = 1997, end_year: Optional[int] = None) -> List[Draw]:
    if end_year is None:
        end_year = datetime.now().year

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    all_draws: List[Draw] = []
    for year in range(start_year, end_year + 1):
        url = ARCHIVE_URL.format(year=year)
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        html = resp.text

        year_draws = try_read_tables(html, year)
        if not year_draws:
            year_draws = parse_from_text(html, year)

        if not year_draws:
            raise RuntimeError(f"Nessuna estrazione trovata per l'anno {year}.")
        all_draws.extend(year_draws)

    all_draws = sorted(dedupe_draws(all_draws), key=lambda x: x.draw_date)
    return all_draws


def draws_to_dataframe(draws: List[Draw]) -> pd.DataFrame:
    rows = []
    for i, draw in enumerate(draws, start=1):
        rows.append({
            "indice_concorso_interno": i,
            "data": pd.to_datetime(draw.draw_date),
            "anno": draw.year,
            "n1": draw.main_numbers[0], "n2": draw.main_numbers[1], "n3": draw.main_numbers[2],
            "n4": draw.main_numbers[3], "n5": draw.main_numbers[4], "n6": draw.main_numbers[5],
            "jolly": draw.jolly, "superstar": draw.superstar,
        })
    return pd.DataFrame(rows)


def score_to_draws(score: float) -> int:
    if score <= 15:
        return 1
    if score <= 30:
        return 2
    if score <= 45:
        return 3
    if score <= 60:
        return 4
    if score <= 75:
        return 5
    return 6


def compute_super_stats(draws: List[Draw]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    total_draws = len(draws)
    today = date.today()

    appearances: Dict[int, int] = {n: 0 for n in range(1, 91)}
    last_seen_idx: Dict[int, Optional[int]] = {n: None for n in range(1, 91)}
    last_seen_date: Dict[int, Optional[date]] = {n: None for n in range(1, 91)}
    max_delay: Dict[int, int] = {n: 0 for n in range(1, 91)}
    prev_seen_idx: Dict[int, Optional[int]] = {n: None for n in range(1, 91)}

    for idx, draw in enumerate(draws):
        current_nums = set(draw.main_numbers)
        for n in range(1, 91):
            if n in current_nums:
                appearances[n] += 1
                gap = idx if prev_seen_idx[n] is None else idx - prev_seen_idx[n] - 1
                max_delay[n] = max(max_delay[n], gap)
                prev_seen_idx[n] = idx
                last_seen_idx[n] = idx
                last_seen_date[n] = draw.draw_date

    for n in range(1, 91):
        trailing_gap = total_draws - 1 - prev_seen_idx[n] if prev_seen_idx[n] is not None else total_draws
        max_delay[n] = max(max_delay[n], trailing_gap)

    stats_rows = []
    base_prob = 6 / 90
    delay_values = []
    freq_values = []

    for n in range(1, 91):
        ls_idx = last_seen_idx[n]
        current_delay = total_draws if ls_idx is None else total_draws - 1 - ls_idx
        ls_date = last_seen_date[n]
        years_since_last = ((today - ls_date).days / 365.25) if ls_date else None
        draw_share = appearances[n] / total_draws if total_draws else 0
        avg_gap_for_number = (total_draws / appearances[n] - 1) if appearances[n] else float(total_draws)

        delay_values.append(current_delay)
        freq_values.append(appearances[n])

        stats_rows.append({
            "numero": n,
            "frequenza": appearances[n],
            "quota_uscite_%": round(draw_share * 100, 2),
            "ritardo_attuale_concorsi": current_delay,
            "ritardo_massimo_concorsi": max_delay[n],
            "ultima_uscita": ls_date,
            "anni_dall_ultima_uscita": round(years_since_last, 2) if years_since_last is not None else None,
            "ritardo_oltre_media": round(current_delay / max(avg_gap_for_number, 1e-9), 3),
            "probabilita_teorica_reale_%": round(base_prob * 100, 2),
        })

    stats = pd.DataFrame(stats_rows)
    delay_mean = float(pd.Series(delay_values).mean())
    delay_std = float(pd.Series(delay_values).std(ddof=0)) or 1.0
    freq_mean = float(pd.Series(freq_values).mean())
    freq_std = float(pd.Series(freq_values).std(ddof=0)) or 1.0

    stats["z_ritardo"] = (stats["ritardo_attuale_concorsi"] - delay_mean) / delay_std
    stats["z_frequenza_inversa"] = (freq_mean - stats["frequenza"]) / freq_std
    stats["bonus_5_anni"] = stats["anni_dall_ultima_uscita"].fillna(0).apply(lambda x: 1.0 if x >= 5 else x / 5)
    stats["score_grezzo"] = (
        0.55 * stats["z_ritardo"] + 0.30 * stats["z_frequenza_inversa"] + 0.15 * stats["bonus_5_anni"]
    )

    min_score = float(stats["score_grezzo"].min())
    max_score = float(stats["score_grezzo"].max())
    if math.isclose(min_score, max_score):
        stats["indice_statistico_%"] = 50.0
    else:
        stats["indice_statistico_%"] = ((stats["score_grezzo"] - min_score) / (max_score - min_score) * 100).round(2)

    stats["non_esce_da_almeno_5_anni"] = stats["anni_dall_ultima_uscita"].fillna(0) >= 5
    stats["concorsi_consigliati"] = stats["indice_statistico_%"].apply(score_to_draws)
    stats = stats.sort_values(["indice_statistico_%", "ritardo_attuale_concorsi"], ascending=[False, False]).reset_index(drop=True)
    top_delay = stats.sort_values(["ritardo_attuale_concorsi", "indice_statistico_%"], ascending=[False, False]).copy()
    return stats, top_delay


def super_ticket(stats_df: pd.DataFrame, seed: Optional[int]) -> List[int]:
    rnd = random.Random(seed)
    top = stats_df.head(18)["numero"].tolist()
    mid = stats_df.iloc[18:50]["numero"].tolist()
    low = stats_df.iloc[50:]["numero"].tolist()
    ticket = rnd.sample(top, min(2, len(top))) + rnd.sample(mid, min(2, len(mid))) + rnd.sample(low, min(2, len(low)))
    ticket = sorted(list(dict.fromkeys(ticket)))
    pool = stats_df["numero"].tolist()
    while len(ticket) < 6:
        x = rnd.choice(pool)
        if x not in ticket:
            ticket.append(x)
    return sorted(ticket[:6])


def compute_jolly_superstar_stats(draws: List[Draw]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    jolly_counts = {n: 0 for n in range(1, 91)}
    superstar_counts = {n: 0 for n in range(1, 91)}

    for draw in draws:
        if draw.jolly is not None and 1 <= int(draw.jolly) <= 90:
            jolly_counts[int(draw.jolly)] += 1
        if draw.superstar is not None and 1 <= int(draw.superstar) <= 90:
            superstar_counts[int(draw.superstar)] += 1

    jolly_df = pd.DataFrame({
        "numero": list(range(1, 91)),
        "frequenza_jolly": [jolly_counts[n] for n in range(1, 91)],
    }).sort_values(["frequenza_jolly", "numero"], ascending=[False, True]).reset_index(drop=True)

    superstar_df = pd.DataFrame({
        "numero": list(range(1, 91)),
        "frequenza_superstar": [superstar_counts[n] for n in range(1, 91)],
    }).sort_values(["frequenza_superstar", "numero"], ascending=[False, True]).reset_index(drop=True)

    return jolly_df, superstar_df


def suggest_jolly_superstar(draws: List[Draw], seed: Optional[int]) -> Tuple[Optional[int], Optional[int]]:
    rnd = random.Random(seed)
    jolly_df, superstar_df = compute_jolly_superstar_stats(draws)

    jolly_pool = jolly_df.head(15)["numero"].tolist()
    superstar_pool = superstar_df.head(15)["numero"].tolist()

    jolly_pick = rnd.choice(jolly_pool) if jolly_pool else None
    superstar_pick = rnd.choice(superstar_pool) if superstar_pool else None
    return jolly_pick, superstar_pick


# -------------------------------------------------
# LOTTO V2 - NEWS UFFICIALI
# -------------------------------------------------
def extract_lotto_news_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/estrazioni-lotto-simbolotto-" in href or "/news/estrazioni-serali-lotto-simbolotto-" in href:
            if href.startswith("http"):
                links.append(href)
            else:
                links.append("https://www.lotto-italia.it" + href)
    # dedup mantenendo ordine
    out = []
    seen = set()
    for link in links:
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def parse_lotto_date_from_page_text(text: str) -> Optional[date]:
    # prova data nel titolo/contenuto
    m = re.search(r"(\d{1,2})\s+([a-zàéìòù]+)\s+(\d{4})", text.lower())
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS_IT.get(m.group(2).lower())
    year = int(m.group(3))
    if not month:
        return None
    try:
        return date(year, month, day)
    except Exception:
        return None


def parse_lotto_news_page(url: str) -> List[LottoDraw]:
    html = http_get(url)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    text = re.sub(r"\xa0", " ", text)
    text = re.sub(r"\n+", "\n", text)
    draw_date = parse_lotto_date_from_page_text(text)
    if draw_date is None:
        return []

    lines = [x.strip() for x in text.splitlines() if x.strip()]
    draws: List[LottoDraw] = []

    i = 0
    while i < len(lines):
        token = lines[i]
        ruota_match = next((r for r in RUOTE if token.lower() == r.lower()), None)
        if ruota_match:
            nums = []
            j = i + 1
            while j < len(lines) and len(nums) < 5:
                if re.fullmatch(r"\d{1,2}", lines[j]):
                    n = int(lines[j])
                    if 1 <= n <= 90:
                        nums.append(n)
                elif any(lines[j].lower() == r.lower() for r in RUOTE):
                    break
                j += 1

            if len(nums) >= 5:
                draws.append(LottoDraw(draw_date=draw_date, ruota=ruota_match, numeri=nums[:5]))
            i = j
        else:
            i += 1

    # dedup per data+ruota
    out = []
    seen = set()
    for d in draws:
        key = (d.draw_date, d.ruota)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


@st.cache_data(show_spinner=False)
def fetch_lotto_recent_draws(max_articles: int = 24) -> List[LottoDraw]:
    # legge la pagina news ufficiale e analizza gli articoli di estrazione recenti
    index_html = http_get(LOTTO_NEWS_URL)
    links = extract_lotto_news_links(index_html)[:max_articles]

    all_draws: List[LottoDraw] = []
    for link in links:
        try:
            all_draws.extend(parse_lotto_news_page(link))
        except Exception:
            continue

    # dedup globale
    out = []
    seen = set()
    for d in sorted(all_draws, key=lambda x: (x.draw_date, x.ruota)):
        key = (d.draw_date, d.ruota)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def lotto_draws_to_df(draws: List[LottoDraw]) -> pd.DataFrame:
    rows = []
    for d in draws:
        rows.append({
            "data": pd.to_datetime(d.draw_date),
            "ruota": d.ruota,
            "n1": d.numeri[0], "n2": d.numeri[1], "n3": d.numeri[2], "n4": d.numeri[3], "n5": d.numeri[4],
        })
    return pd.DataFrame(rows)


def compute_lotto_stats(draws: List[LottoDraw], ruota: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    ruota_draws = [d for d in draws if d.ruota.lower() == ruota.lower()]
    if not ruota_draws:
        return pd.DataFrame(), pd.DataFrame()

    ruota_draws = sorted(ruota_draws, key=lambda x: x.draw_date)
    total_draws = len(ruota_draws)

    appearances: Dict[int, int] = {n: 0 for n in range(1, 91)}
    last_seen_idx: Dict[int, Optional[int]] = {n: None for n in range(1, 91)}
    max_delay: Dict[int, int] = {n: 0 for n in range(1, 91)}
    prev_seen_idx: Dict[int, Optional[int]] = {n: None for n in range(1, 91)}

    for idx, draw in enumerate(ruota_draws):
        current_nums = set(draw.numeri)
        for n in range(1, 91):
            if n in current_nums:
                appearances[n] += 1
                gap = idx if prev_seen_idx[n] is None else idx - prev_seen_idx[n] - 1
                max_delay[n] = max(max_delay[n], gap)
                prev_seen_idx[n] = idx
                last_seen_idx[n] = idx

    for n in range(1, 91):
        trailing_gap = total_draws - 1 - prev_seen_idx[n] if prev_seen_idx[n] is not None else total_draws
        max_delay[n] = max(max_delay[n], trailing_gap)

    rows = []
    delay_values = []
    freq_values = []
    for n in range(1, 91):
        current_delay = total_draws if last_seen_idx[n] is None else total_draws - 1 - last_seen_idx[n]
        delay_values.append(current_delay)
        freq_values.append(appearances[n])
        rows.append({
            "ruota": ruota,
            "numero": n,
            "frequenza": appearances[n],
            "ritardo_attuale_estrazioni": current_delay,
            "ritardo_massimo_estrazioni": max_delay[n],
        })

    stats = pd.DataFrame(rows)
    delay_mean = float(pd.Series(delay_values).mean())
    delay_std = float(pd.Series(delay_values).std(ddof=0)) or 1.0
    freq_mean = float(pd.Series(freq_values).mean())
    freq_std = float(pd.Series(freq_values).std(ddof=0)) or 1.0

    stats["z_ritardo"] = (stats["ritardo_attuale_estrazioni"] - delay_mean) / delay_std
    stats["z_frequenza_inversa"] = (freq_mean - stats["frequenza"]) / freq_std
    stats["score_grezzo"] = (0.60 * stats["z_ritardo"] + 0.40 * stats["z_frequenza_inversa"])
    min_score = float(stats["score_grezzo"].min())
    max_score = float(stats["score_grezzo"].max())
    if math.isclose(min_score, max_score):
        stats["indice_statistico_%"] = 50.0
    else:
        stats["indice_statistico_%"] = ((stats["score_grezzo"] - min_score) / (max_score - min_score) * 100).round(2)

    stats["giocate_consigliate"] = stats["indice_statistico_%"].apply(score_to_draws)
    stats = stats.sort_values(["indice_statistico_%", "ritardo_attuale_estrazioni"], ascending=[False, False]).reset_index(drop=True)
    top_delay = stats.sort_values(["ritardo_attuale_estrazioni", "indice_statistico_%"], ascending=[False, False]).copy()
    return stats, top_delay


def lotto_ticket(stats_df: pd.DataFrame, seed: Optional[int], how_many: int = 5) -> List[int]:
    if stats_df.empty:
        return []
    rnd = random.Random(seed)
    top = stats_df.head(18)["numero"].tolist()
    mid = stats_df.iloc[18:45]["numero"].tolist()
    low = stats_df.iloc[45:]["numero"].tolist()
    picks = []
    if top:
        picks += rnd.sample(top, min(2, len(top)))
    if mid:
        picks += rnd.sample(mid, min(2, len(mid)))
    if low and how_many - len(set(picks)) > 0:
        picks += rnd.sample(low, min(how_many - len(set(picks)), len(low)))
    picks = sorted(list(dict.fromkeys(picks)))
    pool = stats_df["numero"].tolist()
    while len(picks) < how_many:
        x = rnd.choice(pool)
        if x not in picks:
            picks.append(x)
    return sorted(picks[:how_many])


def build_download_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


# -------------------------------------------------
# APP
# -------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Analizzatore Lotterie PRO v2", layout="wide")
    st.title("Analizzatore Lotterie PRO v2")
    st.caption("SuperEnalotto completo + Lotto città/ruote calcolato dalle news ufficiali recenti.")

    tab1, tab2 = st.tabs(["SuperEnalotto", "Lotto città / ruote v2"])

    with tab1:
        with st.sidebar:
            st.header("Impostazioni SuperEnalotto")
            start_year = st.number_input("Anno iniziale", min_value=1997, max_value=datetime.now().year, value=1997, step=1)
            end_year = st.number_input("Anno finale", min_value=1997, max_value=datetime.now().year, value=datetime.now().year, step=1)
            seed_super = st.text_input("Seed casuale opzionale", "")
            st.markdown("---")
            st.info("L'indice statistico non è una probabilità reale: serve solo a ordinare i numeri per ritardo/frequenza.")

        if start_year <= end_year:
            if st.button("Aggiorna dati e analizza SuperEnalotto", use_container_width=True):
                with st.spinner("Scarico lo storico e calcolo le statistiche..."):
                    draws = fetch_super_draws(int(start_year), int(end_year))
                    draws_df = draws_to_dataframe(draws)
                    stats_df, delay_df = compute_super_stats(draws)

                col1, col2, col3 = st.columns(3)
                col1.metric("Estrazioni lette", len(draws_df))
                col2.metric("Intervallo", f"{start_year} - {end_year}")
                col3.metric("Probabilità teorica reale per numero", "6,67%")

                st.warning(
                    "Ogni numero ha la stessa probabilità teorica di uscire al prossimo concorso (6 su 90 = 6,67%). "
                    "La colonna 'indice statistico %' è una stima descrittiva basata su ritardo e frequenza storica, non una previsione certa."
                )

                seed = int(seed_super) if seed_super.strip().isdigit() else None
                ticket = super_ticket(stats_df, seed)
                jolly_pick, superstar_pick = suggest_jolly_superstar(draws, seed)
                pick_df = stats_df[stats_df["numero"].isin(ticket)]
                jolly_df, superstar_df = compute_jolly_superstar_stats(draws)

                st.subheader("Schedina suggerita")
                st.write(" • ".join(str(x) for x in ticket))
                colj1, colj2 = st.columns(2)
                with colj1:
                    st.metric("Jolly suggerito", "-" if jolly_pick is None else str(jolly_pick))
                with colj2:
                    st.metric("Superstar suggerito", "-" if superstar_pick is None else str(superstar_pick))
                st.info(f"Consiglio statistico: mantenerla per circa **{max(1, round(pick_df['concorsi_consigliati'].mean()))} concorsi**.")

                show_cols = [
                    "numero", "frequenza", "ritardo_attuale_concorsi", "ritardo_massimo_concorsi",
                    "ultima_uscita", "anni_dall_ultima_uscita", "non_esce_da_almeno_5_anni",
                    "probabilita_teorica_reale_%", "indice_statistico_%", "concorsi_consigliati"
                ]

                left, right = st.columns(2)
                with left:
                    st.subheader("Top 20 indice statistico")
                    st.dataframe(stats_df[show_cols].head(20), use_container_width=True, hide_index=True)
                with right:
                    st.subheader("Top 20 ritardatari")
                    st.dataframe(delay_df[show_cols].head(20), use_container_width=True, hide_index=True)

                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("Top 15 frequenza")
                    st.bar_chart(stats_df.nlargest(15, "frequenza")[["numero", "frequenza"]].set_index("numero"))
                with c2:
                    st.subheader("Top 15 ritardo")
                    st.bar_chart(stats_df.nlargest(15, "ritardo_attuale_concorsi")[["numero", "ritardo_attuale_concorsi"]].set_index("numero"))

                cj1, cj2 = st.columns(2)
                with cj1:
                    st.subheader("Top 15 Jolly più frequenti")
                    st.dataframe(jolly_df.head(15), use_container_width=True, hide_index=True)
                    st.bar_chart(jolly_df.head(15).set_index("numero")[["frequenza_jolly"]])
                with cj2:
                    st.subheader("Top 15 Superstar più frequenti")
                    st.dataframe(superstar_df.head(15), use_container_width=True, hide_index=True)
                    st.bar_chart(superstar_df.head(15).set_index("numero")[["frequenza_superstar"]])

                st.download_button(
                    "Scarica statistiche CSV",
                    data=build_download_csv(stats_df),
                    file_name="superenalotto_statistiche.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                st.download_button(
                    "Scarica statistiche Jolly CSV",
                    data=build_download_csv(jolly_df),
                    file_name="superenalotto_jolly_statistiche.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                st.download_button(
                    "Scarica statistiche Superstar CSV",
                    data=build_download_csv(superstar_df),
                    file_name="superenalotto_superstar_statistiche.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
        else:
            st.error("L'anno iniziale non può essere maggiore dell'anno finale.")

    with tab2:
        st.subheader("Lotto con città / ruote v2")
        st.caption(
            "Questa v2 legge le news ufficiali recenti delle estrazioni Lotto e calcola frequenze/ritardi per la ruota scelta."
        )
        ruota = st.selectbox("Scegli la ruota", RUOTE, index=5)
        max_articles = st.slider("Quante news recenti analizzare", min_value=8, max_value=40, value=24, step=4)
        seed_lotto = st.text_input("Seed casuale opzionale Lotto", "", key="lotto_seed_v2")

        if st.button("Carica dati Lotto v2", use_container_width=True):
            with st.spinner("Leggo le news ufficiali recenti del Lotto e calcolo le statistiche della ruota scelta..."):
                lotto_draws = fetch_lotto_recent_draws(max_articles=max_articles)
                lotto_df = lotto_draws_to_df(lotto_draws)
                stats_df, delay_df = compute_lotto_stats(lotto_draws, ruota)

            if lotto_df.empty or stats_df.empty:
                st.error("Non sono riuscito a ricostruire dati Lotto sufficienti per questa ruota.")
            else:
                st.info(
                    f"Analisi costruita su **{lotto_df['data'].nunique()} date di estrazione recenti** ricavate dalle news ufficiali. "
                    "Questa sezione è una statistica recente, non uno storico totale dal 1939."
                )

                c1, c2, c3 = st.columns(3)
                c1.metric("Righe ruota lette", len(lotto_df[lotto_df['ruota'] == ruota]))
                c2.metric("Ruota", ruota)
                c3.metric("Date estrazione recenti", int(lotto_df['data'].nunique()))

                seed = int(seed_lotto) if seed_lotto.strip().isdigit() else None
                ticket = lotto_ticket(stats_df, seed, how_many=5)
                pick_df = stats_df[stats_df["numero"].isin(ticket)]

                st.subheader(f"Schedina suggerita per {ruota}")
                st.write(" • ".join(str(x) for x in ticket))
                st.info(f"Consiglio statistico: mantenerla per circa **{max(1, round(pick_df['giocate_consigliate'].mean()))} estrazioni**.")

                show_cols = [
                    "ruota", "numero", "frequenza", "ritardo_attuale_estrazioni",
                    "ritardo_massimo_estrazioni", "indice_statistico_%", "giocate_consigliate"
                ]

                left, right = st.columns(2)
                with left:
                    st.subheader("Top 20 indice statistico")
                    st.dataframe(stats_df[show_cols].head(20), use_container_width=True, hide_index=True)
                with right:
                    st.subheader("Top 20 ritardatari")
                    st.dataframe(delay_df[show_cols].head(20), use_container_width=True, hide_index=True)

                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("Top 15 frequenza")
                    st.bar_chart(stats_df.nlargest(15, "frequenza")[["numero", "frequenza"]].set_index("numero"))
                with c2:
                    st.subheader("Top 15 ritardo")
                    st.bar_chart(stats_df.nlargest(15, "ritardo_attuale_estrazioni")[["numero", "ritardo_attuale_estrazioni"]].set_index("numero"))

                st.subheader("Estratti recenti usati per il calcolo")
                st.dataframe(lotto_df[lotto_df["ruota"] == ruota].sort_values("data", ascending=False), use_container_width=True, hide_index=True)

                st.download_button(
                    f"Scarica CSV Lotto {ruota}",
                    data=build_download_csv(stats_df),
                    file_name=f"lotto_{ruota.lower()}_v2.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        st.markdown("---")
        st.caption(
            "Nota: la v2 delle città usa articoli ufficiali recenti delle estrazioni, perché la sezione statistiche per ruota del sito ufficiale può non esporre una tabella leggibile. "
            "Quindi qui hai un'analisi recente delle ruote, utile e più stabile."
        )


if __name__ == "__main__":
    main()
