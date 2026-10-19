# bimby-sync

Trasforma le ricette della **Mia settimana** di Cookidoo in una **lista della spesa con le quantità sommate**, pronta per **Promemoria** sull'iPhone.

**Cosa fa:**
1. Prende **tutte le ricette pianificate da oggi in avanti**, anche nelle settimane successive.
2. Le mette nella lista della spesa di Cookidoo (non devi più premere "Aggiungi alla lista della spesa") e toglie quelle non più pianificate.
3. **Somma gli ingredienti** per nome e unità di misura (una ricetta pianificata due volte conta due volte) e scrive `spesa.txt`, una riga per prodotto, ad esempio `Pasta – 1,04 kg`.
4. Il Comando Rapido **"Spesa Bimby"** sull'iPhone porta quella lista nell'elenco **Spesa** di Promemoria.

Gira su GitHub Actions **ogni ora** (circa dalle 7 alle 23) e quando premi il pulsante sull'iPhone.

> Progetto personale, non ufficiale: usa la libreria community [`cookidoo-api`](https://github.com/miaucl/cookidoo-api), non affiliata a Vorwerk. Se Cookidoo cambia qualcosa può smettere di funzionare finché la libreria non viene aggiornata.

## 1. Inserisci le credenziali (una volta sola)

Repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Nome | Valore |
|---|---|
| `COOKIDOO_EMAIL` | l'email del tuo account Cookidoo |
| `COOKIDOO_PASSWORD` | la password di Cookidoo |

I Secrets sono cifrati: non compaiono nel codice né nei log.

## 2. Prima prova a secco

**Actions** → **Sincronizza spesa Bimby** → **Run workflow** → spunta **Prova a secco** → **Run workflow**.

Apri l'esecuzione: il log mostra le ricette pianificate, cosa aggiungerebbe o toglierebbe dalla lista Cookidoo e la lista sommata, **senza modificare nulla**. La lista sommata nella prova a secco include solo le ricette già presenti nella lista Cookidoo. Se è tutto giusto, rilancialo senza spunta.

## 3. Token per l'iPhone

github.com → foto profilo → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**:
- Repository access: **Only select repositories** → `bimby-sync`
- Repository permissions: **Actions: Read and write** e **Contents: Read-only**
- Scadenza: 1 anno (poi lo rigeneri)

Copia il token: lo userai solo nel Comando Rapido. Non condividere il Comando Rapido con altri.

## 4. Elenco in Promemoria

Crea in Promemoria un elenco chiamato esattamente **Spesa** (puoi condividerlo con la famiglia). Lì metti a mano anche i prodotti extra: il Comando Rapido tocca **solo** le righe con la nota **Bimby**.

## 5. Comando Rapido "Spesa Bimby"

Nell'app **Comandi** → **+**, aggiungi le azioni in quest'ordine. Le etichette possono variare un po' con la versione di iOS.

**Ricalcola la lista**
1. **Ottieni contenuti dell'URL**
   - URL: `https://api.github.com/repos/enzoruggieroo/bimby-sync/actions/workflows/sync.yml/dispatches`
   - Metodo: **POST** · Corpo richiesta: **JSON** con campo `ref` (testo) = `main`
   - Intestazioni: `Authorization` = `Bearer IL-TUO-TOKEN` · `Accept` = `application/vnd.github+json`
2. **Attendi** 75 secondi.

**Scarica la lista**

3. **Ottieni contenuti dell'URL**
   - URL: `https://api.github.com/repos/enzoruggieroo/bimby-sync/contents/spesa.txt`
   - Metodo: **GET**
   - Intestazioni: `Authorization` = `Bearer IL-TUO-TOKEN` · `Accept` = `application/vnd.github.raw+json`
4. **Testo**: premi Invio, inserisci la variabile *Contenuti dell'URL*, premi Invio. In pratica è la lista con una riga vuota prima e dopo. Rinomina la variabile in **Lista**.
5. **Dividi testo**: *Contenuti dell'URL* per **Nuove righe**. Rinomina in **Righe**.

**Togli le righe Bimby non più necessarie**

6. **Trova promemoria** dove *Elenco* è **Spesa** e *Note* è **Bimby**. Non filtrare per completati: servono tutti.
7. **Ripeti con ciascuno** (i promemoria trovati):
   - **Testo**: Invio, *Ripeti elemento → Titolo*, Invio.
   - **Se** *Lista* **contiene** il *Testo* appena creato → non fare nulla. **Altrimenti** → **Rimuovi promemoria** *Ripeti elemento*.

**Aggiungi le righe nuove**

8. **Ripeti con ciascuno** (*Righe*):
   - **Se** *Ripeti elemento* **ha qualsiasi valore**:
     - **Trova promemoria** dove *Elenco* è **Spesa** e *Titolo* è *Ripeti elemento*.
     - **Se** *Promemoria* **non ha alcun valore** → **Aggiungi nuovo promemoria** *Ripeti elemento* in **Spesa**, con **Note** = `Bimby`.
9. **Mostra notifica**: "Spesa aggiornata 🛒".

Chiamalo **Spesa Bimby**. Puoi avviarlo dalla schermata Home o con *"Ehi Siri, Spesa Bimby"*.

### Come si comporta
- **Righe già spuntate** (comprate) che sono ancora uguali **restano spuntate** e non ricompaiono.
- Se una quantità cambia (es. aggiungi una ricetta e la cipolla passa da `Cipolla – 3` a `Cipolla – 4`), la vecchia riga sparisce e compare quella nuova da comprare.
- Le righe Bimby che non servono più (ricetta cucinata o tolta) vengono rimosse, anche se spuntate.
- **I tuoi prodotti extra non vengono mai toccati.**
- Per una spesa "da zero": in Promemoria → elenco Spesa → **⋯** → **Cancella completati**, poi premi Spesa Bimby.
- Se la notifica arriva ma la lista non riflette l'ultima modifica alla settimana, GitHub era lento: ripremi il comando.

## Limiti
- Si sommano solo prodotti con **stesso nome e stessa unità**: `Cipolla – 1` e `Cipolla – 50 g` restano su righe separate.
- Degli intervalli (`40 - 60 g`) si prende il valore più alto.
- Lo script non sa cosa hai già in casa: se hai già comprato per alcuni giorni e rigeneri, quei prodotti compaiono di nuovo solo se la loro riga è cambiata.

## Sviluppo
```bash
pip install -r requirements.txt pytest
python -m pytest -q
```
