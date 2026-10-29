# Verifica del campionamento del contrasto

Data: 29 ottobre 2026. Base: `2890ee63246b1400919226a8c50beb18e9c86cb0`.

## Modifica

`contrast_limits()` seleziona al massimo `max_samples` indici equidistanti
lungo l'intero array appiattito, mediante `np.linspace(..., dtype=np.intp)`.
Con almeno due campioni sono inclusi il primo e l'ultimo elemento. Un limite
di un solo campione continua a selezionare il primo elemento; limiti non
positivi producono ora un `ValueError` esplicito.

Rimangono invariati l'esclusione del canale alpha, il filtraggio di NaN e
infinito dopo il campionamento, i percentili predefiniti 1 e 99 e i valori
di ripiego per immagini vuote, prive di campioni finiti o costanti.
La modifica riguarda i limiti di visualizzazione: non converte né modifica
i dati originali e non cambia il calcolo delle statistiche scientifiche.

È aggiornata anche la copia già tracciata in
`build/lib/tiff_viewer/image_processing.py`. La prova di creazione del wheel
ha riprodotto l'inclusione della copia vecchia quando sorgente e file di build
avevano la stessa data di modifica. Mantenere identiche le due copie evita
di distribuire ancora il difetto in questa situazione.

## Test effettivamente eseguiti

Ambiente: Linux x86_64, Python 3.12.14, NumPy 2.3.5, Pillow 12.3.0,
setuptools 84.1.0. I test usano `unittest` e array sintetici in memoria.

Comando della suite completa:

```bash
python -m unittest discover -s tests -v
```

- Suite originale sulla base: **7 test superati**.
- Suite ampliata prima della correzione: **18 metodi di test**, con
  **34 fallimenti di sottocasi e 1 errore**. L'errore è la divisione per zero
  con `max_samples=0`; un fallimento riguarda il limite negativo. Gli altri
  33 riguardano la distribuzione del campione o i percentili.
- Suite ampliata dopo la correzione: **18 test superati**, in circa 1,1 s.
- Wheel creato in una cartella temporanea con
  `setuptools.build_meta.build_wheel('dist')`, imponendo date uguali al
  sorgente e alla copia di build: il modulo incluso coincide byte per byte
  con quello corretto. Gli stessi **18 test superati** usando il pacchetto
  estratto dal wheel, da una directory esterna ai sorgenti.
- `git diff --check`: superato.

I test di regressione verificano:

| Caso | Verifica |
|---|---|
| 1.000.001; 1.001.000; 1.500.000; 1.999.000; 2.001.000; 2.500.000; 5.013.504 elementi | Gradienti `float32` e `float64`: confronto P1/P99 con l'intero array, tolleranza assoluta 1 unità su un gradiente a passo 1 |
| Le stesse dimensioni | Campione non superiore a un milione, copertura dei due estremi, indici distinti con spaziatura uniforme entro un elemento |
| Immagini con terzo inferiore luminoso e ordine spaziale invertito | P1/P99 identici al calcolo completo; anche viste non contigue |
| Gradienti con NaN, +∞ e −∞ sparsi oppure in blocchi | Confronto con tutti i valori finiti; tolleranza assoluta 0,01 su un intervallo di intensità di 200 |
| Immagini piccole e da esattamente un milione di elementi | Percentili esatti su tutti i valori finiti |
| Limiti di campionamento 1, 2, 7, 100, 101 e 102 | Rispetto del limite; comportamento agli estremi e sotto soglia |
| Immagini vuote, interamente non finite o costanti | Conservazione dei valori di ripiego |
| Dati `uint16`, `float32`, `float64`, anche in sola lettura | Dati e dtype invariati, risultato deterministico, min/max e conteggi completi invariati |
| RGB/RGBA, anche non contigui | Esclusione di alpha e coerenza con gli stessi canali RGB |

I sette test preesistenti continuano a coprire anche conversione di
visualizzazione, clipping, inversione, RGB e persistenza della calibrazione.

### Confronti numerici eseguiti

Per un gradiente `float64` da 0 a 1, P99 sull'immagine completa vale 0,99:

| Pixel | P99 precedente | P99 corretto |
|---:|---:|---:|
| 1.001.000 | 0,9890109880 | 0,9899990110 |
| 1.500.000 | 0,6599997800 | 0,9899993400 |
| 1.999.000 | 0,4952473763 | 0,9899995048 |
| 2.500.000 | 0,7919995248 | 0,9899996080 |

Per l'immagine 1500×1000 con intensità 10 nei primi due terzi e 1000
nell'ultimo terzo, il codice precedente restituisce `(10, 11)` per via del
ripiego per campioni costanti. Il codice corretto restituisce `(10, 1000)`,
come il calcolo completo.

## Verifiche ancora necessarie e limiti

- Prova su TIFF microscopici reali con fondi variabili, strutture sparse,
  diversi orientamenti e dati `float32`/`float64`.
- Prova interattiva del visualizzatore su Linux e Windows: apertura e cambio
  pagina, contrasto, lettura intensità, informazioni scientifiche, misure,
  zoom e PNG esportato. Nessuna sessione GUI è stata eseguita.
- Installazione completa con dipendenze e launcher sulle piattaforme
  supportate. La prova del wheel non equivale a questa verifica:
  `tifffile` non era installato nell'ambiente usato per i test numerici.
- Misura di tempi e memoria su immagini molto grandi e macchine di utilizzo.
  Il nuovo vettore di indici ha dimensione limitata a `max_samples`;
  non è stato eseguito un benchmark di prestazioni.
- Compatibilità con altre versioni supportate di Python e NumPy; non è
  stata eseguita una matrice di ambienti.

Il campionamento deterministico rimane un'approssimazione: distribuzioni
periodiche o strutture molto sparse possono essere poco rappresentate.
Inoltre il numero di valori finiti può essere inferiore al limite, perché
il filtraggio avviene dopo la selezione. Le tolleranze dei test valgono per
le immagini sintetiche descritte e non sono garanzie generali sull'errore
dei percentili. Non viene cambiato il campionamento di altre funzionalità.
