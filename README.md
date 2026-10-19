# bimby-sync

Trasforma le ricette della **Mia settimana** di Cookidoo in una **lista della spesa con le quantità sommate**, pronta per **Promemoria** sull'iPhone.

**Cosa fa:**
1. Prende **tutte le ricette pianificate da oggi in avanti**, anche nelle settimane successive.
2. Le mette nella lista della spesa di Cookidoo (non devi più premere "Aggiungi alla lista della spesa") e toglie quelle non più pianificate.
3. Cookidoo **somma gli ingredienti**; lo script scrive anche una sua versione sommata in `spesa.txt` (una ricetta pianificata due volte conta due volte).
4. Il Comando Rapido **"Spesa Bimby"** esporta la lista dall'app Bimby e la porta nell'elenco **Spesa** di Promemoria.

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

## 3. Elenco in Promemoria

Crea in Promemoria un elenco chiamato esattamente **Spesa** (puoi condividerlo con la famiglia). Lì metti a mano anche i prodotti extra: il Comando Rapido tocca **solo** le righe con la nota **Bimby**.

## 4. Comando Rapido "Spesa Bimby"

Usa l'azione dell'app Bimby **Esportazione della lista della spesa**, che restituisce la lista di Cookidoo **già sommata** (es. `110 g di olio extravergine di oliva`). Non servono token né attese: GitHub tiene la lista Cookidoo allineata alla settimana ogni ora.

Nell'app **Comandi** → **+**, aggiungi le azioni in quest'ordine (⏎ = vai a capo):

1. **Esportazione della lista della spesa** (app Bimby)
2. **Testo**: ⏎, variabile *Esportazione della lista della spesa*, ⏎
3. **Imposta variabile** → nome **Lista**, valore *Testo*
4. **Dividi testo**: *Esportazione della lista della spesa* per **Nuove righe**
5. **Imposta variabile** → nome **Righe**, valore *Testo diviso*
6. **Trova promemoria** con filtri: *Elenco* è **Spesa** · *Note* contiene `Bimby`
7. **Ripeti con ciascuno** (i promemoria trovati):
   - **Testo**: ⏎, *Ripeti elemento → Titolo*, ⏎
   - **Se** *Lista* **non contiene** *Testo* → **Rimuovi promemoria** *Ripeti elemento*
8. **Ripeti con ciascuno** (*Righe*):
   - **Se** *Ripeti elemento* **ha qualsiasi valore**:
     - **Trova promemoria**: *Elenco* è **Spesa** · *Titolo* è *Ripeti elemento*
     - **Se** *Promemoria* **non ha alcun valore** → **Aggiungi nuovo promemoria** *Ripeti elemento* in **Spesa**, con **Note** = `Bimby`
9. **Mostra notifica**: "Spesa aggiornata 🛒"

### Come si comporta
- **Righe già spuntate** (comprate) che sono ancora uguali **restano spuntate** e non ricompaiono.
- Se una quantità cambia (es. aggiungi una ricetta), la vecchia riga sparisce e compare quella nuova da comprare.
- Le righe Bimby che non servono più vengono rimosse, anche se spuntate.
- **I tuoi prodotti extra non vengono mai toccati.**
- Per una spesa "da zero": in Promemoria → elenco Spesa → **⋯** → **Cancella completati**, poi premi Spesa Bimby.

### Opzionale: ricalcolo immediato
Se hai appena cambiato la settimana e non vuoi aspettare il giro orario, metti **all'inizio** del comando:
1. **Ottieni contenuti dell'URL** → `https://api.github.com/repos/enzoruggieroo/bimby-sync/actions/workflows/sync.yml/dispatches`, metodo **POST**, intestazioni `Authorization` = `Bearer IL-TUO-TOKEN` e `Accept` = `application/vnd.github+json`, corpo **JSON** con `ref` = `main`
2. **Attendi** 75 secondi

Il token (fine-grained, solo repository `bimby-sync`, permesso **Actions: Read and write**) si crea da github.com → Settings → Developer settings → Personal access tokens.

## Limiti
- Si sommano solo prodotti con **stesso nome e stessa unità**: `Cipolla – 1` e `Cipolla – 50 g` restano su righe separate.
- Degli intervalli (`40 - 60 g`) si prende il valore più alto.
- Lo script non sa cosa hai già in casa: se hai già comprato per alcuni giorni e rigeneri, quei prodotti compaiono di nuovo solo se la loro riga è cambiata.

## Sviluppo
```bash
pip install -r requirements.txt pytest
python -m pytest -q
```
