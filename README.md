# bimby-sync

Trasforma le ricette della **Mia settimana** di Cookidoo in una **lista della spesa con le quantità sommate**, pronta per **Promemoria** sull'iPhone.

**Cosa fa:**
1. Prende **tutte le ricette pianificate da oggi in avanti**, anche nelle settimane successive.
2. Le mette nella lista della spesa di Cookidoo (non devi più premere "Aggiungi alla lista della spesa") e toglie quelle non più pianificate.
3. Cookidoo **somma gli ingredienti**; lo script scrive anche una sua versione sommata in `spesa.txt` (una ricetta pianificata due volte conta due volte).
4. Il Comando Rapido **"Spesa"** esporta la lista dall'app Bimby e la porta nell'elenco **Lista spesa** di Promemoria; i prodotti spuntati lì vengono segnati come già in casa in Cookidoo.

Gira quando premi "Spesa", quando esci dall'app Bimby e, come riserva, con i controlli programmati di GitHub (che GitHub esegue solo alcune volte al giorno).

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

Crea in Promemoria un elenco chiamato esattamente **Lista spesa** (puoi condividerlo con la famiglia). Lì metti a mano anche i prodotti extra: il Comando Rapido tocca **solo** le righe con la nota **Bimby**.

## 4. Comando Rapido "Spesa"

Crea un token fine-grained (github.com → Settings → Developer settings → Personal access tokens) con accesso solo a `bimby-sync` e permesso **Actions: Read and write**.

Azioni, in quest'ordine:

1. **Trova promemoria**: *Elenco* è **Lista spesa** · *Note* contiene `Bimby` · *Completato* è **Sì**
2. **Combina testo**: *Promemoria* con **Nuove righe**
3. **Ottieni contenuti dell'URL** → `https://api.github.com/repos/enzoruggieroo/bimby-sync/actions/workflows/sync.yml/dispatches`
   - Metodo **POST** · intestazioni `Authorization` = `Bearer IL-TUO-TOKEN`, `Accept` = `application/vnd.github+json`
   - Corpo **JSON**: `ref` = `main` · `inputs` (dizionario) → `comprati` = *Testo combinato*
4. **Attendi** 30 secondi
5. **Esportazione della lista della spesa** (app Bimby): la lista già sommata da Cookidoo
6. **Corrispondenza testo** `.+` su *Esportazione della lista della spesa*
7. **Trova promemoria**: *Elenco* è **Lista spesa** · *Note* contiene `Bimby`
8. **Rimuovi promemoria** *Promemoria* (iOS chiede sempre conferma)
9. **Ripeti con ciascun elemento** in *Risultati* → **Aggiungi nuovo promemoria** *Elemento ripetizione* in **Lista spesa**, Note `Bimby`
10. **Mostra notifica**

### Come si comporta
- I prodotti **spuntati** in Promemoria vengono segnati in Cookidoo come **già in casa** e non tornano più.
- Le altre righe Bimby vengono riscritte da capo con la lista aggiornata.
- I prodotti aggiunti a mano (senza nota `Bimby`) **non vengono mai toccati**.

## 5. Automazione "quando chiudo l'app Bimby"

Comando **Aggiorna Bimby** con la sola azione 3 (senza `inputs`). Automazione: **App → Bimby → È chiusa → Esegui immediatamente → Esegui comando rapido "Aggiorna Bimby"**. Ogni volta che esci dall'app, le ricette nuove della settimana entrano nella lista Cookidoo.

## Limiti
- Si sommano solo prodotti con **stesso nome e stessa unità**: `Cipolla – 1` e `Cipolla – 50 g` restano su righe separate.
- Degli intervalli (`40 - 60 g`) si prende il valore più alto.
- Lo script non sa cosa hai già in casa: se hai già comprato per alcuni giorni e rigeneri, quei prodotti compaiono di nuovo solo se la loro riga è cambiata.

## Sviluppo
```bash
pip install -r requirements.txt pytest
python -m pytest -q
```
