# Radar SAP

Radar giornaliero delle notizie del mondo SAP e dei tool esterni che funzionano bene
sulla nostra soluzione, con una dashboard interattiva pubblicata su GitHub Pages.

**Dashboard:** https://w8997wnwy5-collab.github.io/news_work/ (attiva dopo il passo 1 qui sotto)

Ogni mattina il tool legge le fonti configurate, tiene solo quello che riguarda il
nostro stack, assegna una categoria e un punteggio di rilevanza, e aggiorna la
dashboard. Nessuna azione manuale richiesta.

**Profilo della soluzione su cui è tarato il radar**

> S/4HANA private cloud / on-premise (percorso RISE e clean core), esteso e integrato
> tramite SAP BTP: Integration Suite (CPI), estensioni ABAP Cloud / CAP, Build e
> Datasphere. Aree seguite: Finance, Logistica, HR & Procurement SaaS, Tech
> (Basis, Security, ABAP, AI).

---

## Cosa vedi nella dashboard

**Notizie** — il flusso filtrabile. Ogni scheda porta:

| Pulsante | Dove va |
|---|---|
| Apri l'articolo | la fonte originale |
| Post LinkedIn | la ricerca LinkedIn sui post che parlano proprio di quella notizia, ordinati per data |
| Documentazione SAP | l'hub `help.sap.com` dell'area della notizia |
| Demo / contatto | solo sulle notizie dei vendor: la pagina demo o contatto di quel vendor |

Filtri disponibili: periodo (24h / 7 giorni / 30 giorni / tutto), categoria, tipo di
fonte, ricerca testuale, "solo da leggere", "nascondi già lette", "solo salvate".
Ordinamento per rilevanza o per data.

Cosa hai letto e cosa hai salvato resta nel tuo browser (`localStorage`), quindi ognuno
ha la propria lista senza pestarsi i piedi. **Copia digest** mette negli appunti le
notizie visibili in markdown, pronte da incollare in chat o in una mail.

**Vendor & Tool** — il catalogo dei tool esterni. Per ognuno: cosa fa, perché ha senso
sulla nostra soluzione, con quali componenti si integra, il livello di certificazione
SAP, e i link a documentazione, demo/call e pagina LinkedIn.

**Controllo** — lo stato di salute del radar: quali fonti hanno risposto, quando hanno
funzionato l'ultima volta, quali link del catalogo sono rotti, e come sono tarate le
soglie di rilevanza.

---

## Come funziona

```
config/*.yaml  ->  fetch  ->  classify  ->  store  ->  render  ->  docs/
  (cosa           (RSS/      (categoria   (storico    (dashboard
   seguire)        Atom)      + punteggio) 60 giorni)   + digest)
```

### Il punteggio di rilevanza (0-100)

Ogni notizia somma quattro contributi, tutti dichiarati nello YAML:

1. **Credibilità della fonte** — il campo `peso` in `config/sources.yaml`
   (SAP ufficiale pesa più di un blog vendor).
2. **Aderenza alle categorie** — le `keywords` di `config/taxonomy.yaml`, con tetto a 30 punti.
3. **Aderenza al nostro stack** — `profile.boost` premia i termini che ci riguardano
   (`s/4hana`, `private cloud`, `clean core`, `integration suite`, `abap cloud`...),
   `profile.penalize` abbassa quello che non usiamo (`business one`, `bydesign`...).
   Tetto a 40 punti.
4. **Freschezza** — bonus decrescente: +10 sotto le 24 ore, +6 sotto i 3 giorni.

Il risultato diventa un livello leggibile: **Da leggere** da 70 punti, **Da monitorare**
da 40, sotto resta come informazione. Sotto 15 punti la notizia è considerata rumore e
non entra nemmeno nello storico.

La riga "Agganciata su:" di ogni scheda mostra i termini che hanno fatto scattare il
punteggio: se una notizia ti sembra fuori posto, quella riga dice esattamente perché è
finita li'.

### Le fonti

29 feed divisi in quattro tipi: SAP ufficiale (News Center, SAP Community), community,
stampa e analisti (ERP Today, SAPinsider, E-3, diginomica, The Register), vendor e
partner dell'ecosistema.

Due accorgimenti rendono il radar resistente al tempo:

- **`fallback`** — ogni fonte può dichiarare url alternativi, provati in ordine se il
  principale non risponde. I path RSS di SAP cambiano spesso.
- **`solo_se`** — sulle fonti generaliste tiene solo le voci che contengono certi termini,
  così diginomica non ci porta dentro le notizie su Salesforce.

Una fonte rotta non blocca le altre: viene segnata in rosso nella scheda Controllo.

---

## Uso quotidiano

Non serve fare niente: il workflow gira ogni giorno alle **07:10 italiane**, aggiorna i
dati, li committa e ripubblica la dashboard.

Per lanciarlo a mano: *Actions → Radar SAP - aggiornamento giornaliero → Run workflow*.

### In locale

```bash
pip install -r requirements.txt

python -m sapnews update        # legge le fonti e rigenera tutto
python -m sapnews serve         # dashboard su http://localhost:8000
```

> Apri la dashboard con `serve`, non con doppio clic sul file: aprendola da `file://`
> il browser blocca la lettura di `docs/data/news.json`.

Altri comandi:

```bash
python -m sapnews validate      # controlla la coerenza dei file in config/
python -m sapnews stats         # statistiche correnti in JSON
python -m sapnews check-links   # verifica i link del catalogo vendor
python -m sapnews render        # rigenera dashboard e digest senza toccare la rete
python -m sapnews update --only sap_news_center -v     # prova una sola fonte
python -m sapnews update --fixtures ./feed-locali       # giro offline: legge <id_fonte>.xml
```

---

## Tararlo sulle nostre esigenze

Tutto si cambia nello YAML, senza toccare il codice. Dopo la modifica, `python -m
sapnews update` (o il run automatico del giorno dopo) applica tutto.

### Aggiungere una fonte

```yaml
# config/sources.yaml
  - id: nuovo_blog
    nome: "Nome leggibile"
    tipo: vendor            # official | community | press | vendor
    peso: 10                # quanto è credibile (0-20)
    vendor: id_vendor       # facoltativo: aggancia i pulsanti demo/call
    url: "https://esempio.com/feed/"
    fallback: ["https://esempio.com/rss"]
    solo_se: ["sap"]        # facoltativo: filtro per fonti generaliste
```

### Cambiare cosa consideriamo rilevante

In `config/taxonomy.yaml`, blocco `profile`: aggiungi a `boost` i termini che ci
riguardano e a `penalize` quelli fuori perimetro. Se troppe notizie risultano
"da leggere", alza `soglie.must`.

### Aggiungere un tool al catalogo

In `config/vendors.yaml`. `link.demo` e `link.docs` sono facoltativi: se mancano — o se
il controllo settimanale li trova rotti — la dashboard ripiega automaticamente su
`link.sito`, quindi un pulsante non porta mai su una pagina morta.

---

## Struttura

```
config/
  sources.yaml      le fonti RSS/Atom
  taxonomy.yaml     categorie, parole chiave, profilo della soluzione, soglie
  vendors.yaml      catalogo dei tool esterni
sapnews/
  fetch.py          lettura dei feed, fallback, diagnostica per fonte
  classify.py       categorie e punteggio di rilevanza
  store.py          storico in data/news.json (60 giorni, max 900 notizie)
  render.py         dashboard, dati e digest
  links.py          controllo dei link vendor
  cli.py            comandi
  templates/
    dashboard.html  la dashboard (HTML+CSS+JS, nessuna dipendenza esterna)
data/
  news.json         storico versionato in git: il diff mostra cosa è entrato ogni giorno
docs/               quello che viene pubblicato su GitHub Pages
  index.html        la dashboard
  data/news.json    i dati che legge
  digest.md         il riassunto del giorno in markdown
tests/              test della pipeline, completamente offline
```

---

## Prima attivazione

1. **GitHub Pages**: *Settings → Pages → Source: GitHub Actions*. Da quel momento la
   dashboard vive su https://w8997wnwy5-collab.github.io/news_work/. Senza questo passo il
   workflow continua a funzionare e ad aggiornare i dati nel repository, ma la dashboard
   non viene pubblicata (il run lo segnala con una nota).
2. **Primo run**: *Actions → Radar SAP → Run workflow*, per non aspettare la mattina dopo.
3. Dopo il primo run, il riepilogo del workflow elenca le fonti che non hanno risposto:
   sistema il loro `url` in `config/sources.yaml` oppure rimuovile.

---

## Note

- **Colori**: la palette delle categorie è verificata per daltonismo e contrasto in tema
  chiaro e scuro. Il grafico di distribuzione usa una sola tinta perché misura quantità:
  l'identità della categoria la porta l'etichetta, non il colore.
- **LinkedIn** non espone un feed pubblico e il suo regolamento non consente di
  raccoglierne i contenuti: per questo i pulsanti portano alla ricerca LinkedIn sul tema
  della notizia (ordinata per data) invece che a un post specifico.
- **Privacy**: nessun account, nessun tracciamento. La dashboard è HTML statico; letture
  e preferenze restano nel browser di chi la apre.
