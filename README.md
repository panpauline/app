# licei-trend-iscrizioni

## Ricerca automatica bandi per formatori

Strumento che cerca periodicamente sul web i **bandi/avvisi delle scuole
italiane per la selezione di formatori** collegati all'**Avviso prot. n. 95165
del 24/04/2026** (Programma Nazionale "PN Scuola e competenze 2021-2027") e ad
avvisi analoghi per la formazione del personale docente ed educativo.

### Come funziona

- **`scripts/cerca_bandi.py`** — esegue le ricerche su DuckDuckGo (regione
  Italia), filtra i risultati rilevanti e tiene traccia di quelli gia' visti
  in `dati/visti.json` per non segnalarli due volte.
- **`.github/workflows/ricerca-bandi.yml`** — GitHub Action che:
  - gira automaticamente **ogni 4 giorni** (cron `0 5 */4 * *`, ore 05:00 UTC);
  - apre una **issue su GitHub** con i nuovi bandi trovati (GitHub ti invia
    un'email di notifica);
  - archivia tutto lo storico in `dati/risultati.md`.

### Come attivarla

> [!IMPORTANT]
> Le Action schedulate di GitHub si attivano **solo dal branch principale
> (`main`)**. Per far partire la pianificazione automatica, questo branch va
> unito a `main`.

1. Unisci le modifiche a `main`.
2. Vai su **Settings → Actions → General** e assicurati che i workflow abbiano
   permessi di **lettura e scrittura** ("Read and write permissions").
3. Puoi lanciare una ricerca subito a mano da **Actions → Ricerca bandi
   formatori → Run workflow**.

### Personalizzare la ricerca

Le parole chiave e le query sono in cima a `scripts/cerca_bandi.py`
(sezione *Configurazione*): puoi aggiungerne o modificarle liberamente.
