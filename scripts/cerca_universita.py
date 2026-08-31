#!/usr/bin/env python3
"""Ricerca automatica di bandi APERTI nelle universita' italiane per:

1. DOCENZE A CONTRATTO (art. 23 L. 240/2010) in materie umanistiche affini
   al profilo: italianistica, letteratura, latino, greco, filologia,
   linguistica, glottodidattica, pedagogia, didattica digitale/tecnologie
   didattiche, studi umanistici.
2. TUTOR COORDINATORE / TUTOR ORGANIZZATORE dei percorsi abilitanti per
   docenti (DPCM 4 agosto 2023, 60/30/36 CFU), con priorita' alle classi di
   concorso A11, A12, A13.

REGOLE (vedi istruzioni del progetto):
- Tutte le sedi italiane.
- SOLO avvisi a cui ci si puo' ancora candidare: graduatorie, esiti,
  vincitori/idonei, approvazioni atti e nomine vengono scartati.
- I bandi di TUTORATO PER STUDENTI (assegni L. 170/2003, tutor alla pari,
  magistralisti, dottorandi) NON interessano e vengono scartati.
- Se nel testo compare una scadenza gia' passata o un anno accademico
  troppo vecchio, il risultato viene scartato.

I risultati gia' visti vengono salvati in dati/visti_universita.json. Solo i
risultati NUOVI vengono scritti in nuovi_universita.md, che il workflow usa
per aprire una issue di notifica.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    from duckduckgo_search import DDGS  # type: ignore

# --- Configurazione ----------------------------------------------------------

QUERIES = [
    # Docenza a contratto - discipline del profilo
    'bando docenza a contratto letteratura italiana italianistica universita',
    'bando docenza a contratto latino filologia classica universita',
    'bando docenza a contratto linguistica glottodidattica didattica delle lingue universita',
    'avviso selezione docente a contratto studi umanistici lettere universita',
    'bando docenza a contratto tecnologie didattiche e-learning didattica digitale universita',
    'bando docenza a contratto pedagogia scienze della formazione universita',
    'bando contratti di insegnamento percorsi abilitanti formazione iniziale docenti didattica italiano',
    # Tutor coordinatore / organizzatore dei percorsi abilitanti
    'bando tutor coordinatore percorsi abilitanti universita',
    'selezione tutor coordinatore tutor organizzatore percorsi abilitanti docenti universita',
    'avviso selezione tutor coordinatore percorsi di formazione iniziale docenti 60 CFU',
    'bando tutor coordinatore percorsi abilitanti classe di concorso A11 A12 A13',
    'selezione tutor percorsi abilitanti 30 CFU 60 CFU DPCM 4 agosto 2023 universita',
]

# Figura 1: docenza a contratto / incarichi di insegnamento.
KW_DOCENZA = [
    "docenza a contratto", "docente a contratto", "docenti a contratto",
    "docenze a contratto", "professore a contratto", "professori a contratto",
    "incarico di insegnamento", "incarichi di insegnamento",
    "contratto di insegnamento", "contratti di insegnamento",
    "contratti d'insegnamento", "affidamento di insegnamento",
    "affidamento insegnamenti", "moduli didattici",
]

# Figura 2: tutor dei percorsi abilitanti (NON tutorato per studenti).
KW_TUTOR_ABILITANTI = [
    "tutor coordinatore", "tutor coordinatori", "tutor organizzatore",
    "tutor organizzatori", "tutor dei percorsi", "tutor per i percorsi",
    "percorsi abilitanti", "percorso abilitante", "percorsi di formazione iniziale",
    "formazione iniziale dei docenti", "formazione iniziale docenti",
    "60 cfu", "30 cfu", "36 cfu", "dpcm 4 agosto 2023", "pf60", "pf24",
]

KW_FIGURA = KW_DOCENZA + KW_TUTOR_ABILITANTI

# Deve essere un bando/avviso di selezione.
KW_BANDO = [
    "bando", "avviso", "concorso", "selezione", "manifestazione di interesse",
    "procedura comparativa", "avviso pubblico", "avviso di selezione",
    "call", "reclutamento", "affidamento", "conferimento di incarichi",
    "conferimento incarichi",
]

# Profilo disciplinare (richiesto per le docenze a contratto; per i tutor dei
# percorsi abilitanti la figura stessa e' gia' sufficiente).
KW_PROFILO = [
    "italianistica", "letteratura", "letterari", "letterarie", "latino", "greco",
    "filologia", "filologi", "linguistica", "glottodidattica", "glottologia",
    "lingua italiana", "didattica dell'italiano", "didattica delle lingue",
    "metodologie didattiche", "tecnologie didattiche", "tecnologie dell'educazione",
    "didattica digitale", "e-learning", "digital humanities", "media education",
    "studi umanistici", "scienze umane", "scienze dell'educazione",
    "scienze della formazione", "pedagogi", "lettere", "umanistic",
    "storia", "filosofia", "formazione iniziale", "percorsi abilitanti",
    "abilitant", "classi di concorso", "classe di concorso", "discipline letterarie",
]

# Classi di concorso dell'utente: evidenziate nella notifica.
_CDC_RE = re.compile(r"\ba-?1[123]\b|discipline letterarie", re.I)

# --- Esclusioni ----------------------------------------------------------------

# Tutorato PER STUDENTI: non e' la figura cercata.
KW_STUDENTI = [
    "per studenti", "per gli studenti", "agli studenti", "riservato a studenti",
    "riservata a studenti", "riservato agli studenti", "studenti capaci e meritevoli",
    "170/2003", "tutorato alla pari", "peer tutoring", "magistralisti",
    "borse di collaborazione", "collaborazioni studentesche", "150 ore",
    "part-time", "tutor junior", "matricole", "immatricolati", "dottorandi",
    "dottorato di ricerca", "assegni di tutorato", "assegni per attivita di tutorato",
    "assegni per attivita' di tutorato", "tutorato didattico", "tutorato orientativo",
    "attivita di tutorato", "attivita' di tutorato", "attivita' di tutoraggio",
    "attivita di tutoraggio", "pot ", "piano orientamento e tutorato",
]

# Graduatorie, esiti, atti di selezioni concluse: NON candidabili.
KW_ESITI = [
    "graduatoria", "graduatorie", "esito", "esiti",
    "vincitor", "idonei", "risultati selezion", "risultati della selezione",
    "approvazione atti", "approvazione degli atti", "decreto di approvazione",
    "atti della selezione", "decreto di individuazione", "determina di individuazione",
    "individuato quale", "individuati quali", "verbale", "nomina della commissione",
    "nomina commissione", "scorrimento", "aggiudicazione",
    "conclusa", "concluso", "bando scaduto", "concorso chiuso", "termini scaduti",
    "elenco professori a contratto",  # elenchi trasparenza, non bandi
]

# Domini di news/portali/aggregatori da escludere.
BLOCKLIST = [
    "orizzontescuola.it", "tecnicadellascuola.it", "skuola.net", "studenti.it",
    "tuttoscuola.com", "studentville.it", "wikipedia.org", "uninews24.it",
    "universita.it", "ilfattoquotidiano.it", "repubblica.it", "corriere.it",
    "lastampa.it", "ansa.it", "indeed", "infojobs", "monster.it",
    "linkedin.com", "scuolazoo.com", "miur.gov.it", "mim.gov.it",
    "istruzione.it", "concorsipubblici.com", "profilcultura.it",
    "academicjobsitaly.com", "academia.edu", "lawinsider.com",
]

# Indizi che il dominio appartiene a un'universita' italiana (o al portale
# PICA/CINECA e a inPA, usati da molti atenei per le selezioni).
UNI_HINTS = [
    "uni", "pica.cineca.it", "inpa.gov.it",
    "gssi", "sissa", "iuss", "imtlucca", "scuolanormale", "sns.it",
    "santanna", "santannapisa", "iulm", "luiss", "lumsa", "humanitas",
    "bicocca", "vitaesalute", "vita-salute", "polimi", "polito", "polibz",
    "unicatt", "european-university", "europeanuniversity",
    "concorsi", "bandi",
]

MAX_PER_QUERY = 25
RECENZA = "m"

ANNO_MIN = datetime.now(timezone.utc).year - 1
_ANNO_NEL_PATH = re.compile(r"/(20\d{2})/\d{1,2}/")
# Anno accademico nel testo o nell'URL: "a.a. 2024/2025", "a.a. 2024-25",
# "a-a-2024-25" (nei percorsi URL).
_AA_RE = re.compile(r"a[\.\-\s]?a[\.\-\s]*(20\d{2})\s*[/\-\u2013]\s*(?:20)?\d{2}", re.I)

# --- Filtro sulla data di scadenza -------------------------------------------

_MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
         "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9,
         "ottobre": 10, "novembre": 11, "dicembre": 12}

_SCAD_NUM = re.compile(
    r"(?:scadenza|entro(?:\s+il)?|termine(?:\s+ultimo)?(?:\s+di\s+presentazione)?)"
    r"[^\d]{0,40}(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](20\d{2})", re.I)
_SCAD_TXT = re.compile(
    r"(?:scadenza|entro(?:\s+il)?|termine)"
    r"[^\d]{0,40}(\d{1,2})\u00b0?\s+"
    r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
    r"ottobre|novembre|dicembre)\s+(20\d{2})", re.I)


def scadenza_passata(testo: str) -> bool:
    """True se nel testo compare una data di scadenza gia' trascorsa."""
    oggi = datetime.now(timezone.utc).date()
    t = testo.lower()
    for m in _SCAD_NUM.finditer(t):
        try:
            g, me, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if date(a, me, g) < oggi:
                return True
        except ValueError:
            continue
    for m in _SCAD_TXT.finditer(t):
        try:
            g, a = int(m.group(1)), int(m.group(3))
            if date(a, _MESI[m.group(2)], g) < oggi:
                return True
        except (ValueError, KeyError):
            continue
    return False


def anno_accademico_vecchio(testo: str) -> bool:
    """True se il testo/URL cita un anno accademico chiaramente passato
    (inizio a.a. anteriore all'anno scorso)."""
    for m in _AA_RE.finditer(testo):
        if int(m.group(1)) < ANNO_MIN:
            return True
    return False


# --- Percorsi ---------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATI_DIR = ROOT / "dati"
STATO_FILE = DATI_DIR / "visti_universita.json"
ARCHIVIO_FILE = DATI_DIR / "risultati_universita.md"
NUOVI_FILE = ROOT / "nuovi_universita.md"


def carica_stato() -> set[str]:
    if STATO_FILE.exists():
        data = json.loads(STATO_FILE.read_text(encoding="utf-8"))
        return set(data.get("urls", []))
    return set()


def salva_stato(urls: set[str]) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    STATO_FILE.write_text(
        json.dumps({"urls": sorted(urls)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalizza_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def dominio(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def url_troppo_vecchio(url: str) -> bool:
    m = _ANNO_NEL_PATH.search(url)
    return bool(m) and int(m.group(1)) < ANNO_MIN


def fonte_universita(url: str) -> bool:
    dom = dominio(url)
    if not dom or any(b in dom for b in BLOCKLIST):
        return False
    u = url.lower()
    return any(h in dom for h in UNI_HINTS) or any(h in u for h in UNI_HINTS)


def classifica(testo: str, url: str) -> str | None:
    """Ritorna 'docenza', 'tutor' oppure None se il risultato non e' rilevante
    o non e' candidabile."""
    if not fonte_universita(url):
        return None
    if url_troppo_vecchio(url):
        return None
    t = f"{testo} {url}".lower()
    # Esclusioni forti.
    if any(k in t for k in KW_ESITI):
        return None
    if any(k in t for k in KW_STUDENTI):
        return None
    if scadenza_passata(t) or anno_accademico_vecchio(t):
        return None
    # Deve essere un bando/avviso.
    if not any(k in t for k in KW_BANDO):
        return None
    e_tutor = any(k in t for k in KW_TUTOR_ABILITANTI)
    e_docenza = any(k in t for k in KW_DOCENZA)
    if e_tutor:
        return "tutor"
    if e_docenza and any(k in t for k in KW_PROFILO):
        return "docenza"
    return None


def e_rilevante(testo: str, url: str) -> bool:
    return classifica(testo, url) is not None


def cerca() -> list[dict]:
    trovati: dict[str, dict] = {}
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                risultati = ddgs.text(q, region="it-it", safesearch="off",
                                      max_results=MAX_PER_QUERY,
                                      timelimit=RECENZA)
            except Exception as exc:
                print(f"[warn] query fallita: {q!r} -> {exc}", file=sys.stderr)
                time.sleep(3)
                continue
            for r in risultati or []:
                url = normalizza_url(r.get("href") or r.get("url") or "")
                if not url:
                    continue
                titolo = (r.get("title") or "").strip()
                snippet = (r.get("body") or "").strip()
                testo = f"{titolo} {snippet}"
                tipo = classifica(testo, url)
                if not tipo:
                    continue
                trovati.setdefault(url, {
                    "url": url,
                    "titolo": titolo or url,
                    "snippet": snippet,
                    "query": q,
                    "tipo": tipo,
                    "cdc": bool(_CDC_RE.search(f"{testo} {url}")),
                })
            time.sleep(2)
    return list(trovati.values())


def _riga(r: dict) -> list[str]:
    tag = "\U0001f393 Tutor percorsi abilitanti" if r["tipo"] == "tutor" else "\U0001f4d6 Docenza a contratto"
    if r.get("cdc"):
        tag += " \u2014 \U0001f3af classi A11/A12/A13"
    righe = [f"### [{r['titolo']}]({r['url']})", f"**{tag}**"]
    if r["snippet"]:
        righe.append(f"> {r['snippet']}")
    righe.append(f"`query: {r['query']}`")
    righe.append("")
    return righe


def scrivi_archivio(nuovi: list[dict], quando: str) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    nuovo_file = not ARCHIVIO_FILE.exists()
    with ARCHIVIO_FILE.open("a", encoding="utf-8") as f:
        if nuovo_file:
            f.write("# Archivio docenze a contratto e tutor percorsi abilitanti\n\n")
        f.write(f"## Ricerca del {quando}\n\n")
        for r in nuovi:
            tipo = "tutor abilitanti" if r["tipo"] == "tutor" else "docenza"
            f.write(f"- [{r['titolo']}]({r['url']}) _({tipo})_\n")
            if r["snippet"]:
                f.write(f"  - {r['snippet']}\n")
        f.write("\n")


def scrivi_notifica(nuovi: list[dict], quando: str) -> None:
    tutor = [r for r in nuovi if r["tipo"] == "tutor"]
    docenze = [r for r in nuovi if r["tipo"] == "docenza"]
    righe = [f"@panpauline \u2014 trovati **{len(nuovi)}** nuovi bandi universitari "
             f"candidabili (ricerca del {quando}): {len(tutor)} tutor percorsi "
             f"abilitanti, {len(docenze)} docenze a contratto.",
             "Graduatorie, esiti e tutorati per studenti sono esclusi.", ""]
    if tutor:
        righe.append("## \U0001f393 Tutor coordinatore / organizzatore percorsi abilitanti")
        righe.append("")
        for r in tutor:
            righe.extend(_riga(r))
    if docenze:
        righe.append("## \U0001f4d6 Docenze a contratto")
        righe.append("")
        for r in docenze:
            righe.extend(_riga(r))
    righe.append("---")
    righe.append("_Ricerca automatica. Verifica sempre la fonte ufficiale "
                 "dell'universita' e che la scadenza sia futura prima di "
                 "candidarti._")
    NUOVI_FILE.write_text("\n".join(righe), encoding="utf-8")


def main() -> int:
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    visti = carica_stato()
    risultati = cerca()
    nuovi = [r for r in risultati if r["url"] not in visti]
    print(f"Universita' rilevanti: {len(risultati)} | nuovi: {len(nuovi)}")
    if nuovi:
        scrivi_archivio(nuovi, quando)
        scrivi_notifica(nuovi, quando)
        visti.update(r["url"] for r in nuovi)
        salva_stato(visti)
    else:
        if NUOVI_FILE.exists():
            NUOVI_FILE.unlink()
        salva_stato(visti)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
