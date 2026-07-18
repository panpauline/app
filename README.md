# licei-trend-iscrizioni

## Ricerca automatica bandi (formatori scuole + docenze/tutoraggi universita')

Strumento che cerca periodicamente sul web:

1. **Bandi delle scuole italiane per la selezione di formatori** collegati al
   **DM 38/2026**, all'**Avviso prot. n. 95165 del 24/04/2026** e al programma
   **PN Scuola e competenze 2021-2027**. La ricerca e' limitata alle scuole di
   **Nord e Centro Italia**.
2. **Bandi APERTI per docenze a contratto e tutoraggi** delle universita'
   italiane (pubbliche e private) su materie umanistiche affini al profilo:
   italianistica, latino, filologia, linguistica, didattica, metodologie
   didattiche, pedagogia, studi umanistici.

### Come funziona

- **`scripts/cerca_bandi.py`** — ricerca bandi formatori nelle scuole di
  Nord/Centro (stato: `dati/visti.json`, archivio: `dati/risultati.md`).
- **`scripts/cerca_universita.py`** — ricerca docenze a contratto e tutoraggi
  universitari (stato: `dati/visti_universita.json`, archivio:
  `dati/risultati_universita.md`).
- **`.github/workflows/ricerca-bandi.yml`** — GitHub Action che:
  - gira automaticamente **ogni 4 giorni** (cron `0 5 */4 * *`, ore 05:00 UTC);
  - esegue entrambe le ricerche;
  - apre **due issue separate** su GitHub (una per i formatori, una per le
    docenze/tutoraggi) quando ci sono novita' — GitHub ti invia un'email di
    notifica.

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

### Personalizzare le ricerche

Le parole chiave e le query sono in cima a ciascuno script
(`scripts/cerca_bandi.py`, `scripts/cerca_universita.py`), nella sezione
*Configurazione*: puoi aggiungerne o modificarle liberamente.
