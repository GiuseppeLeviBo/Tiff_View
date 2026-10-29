# Verifica del packaging

Data: 29 ottobre 2026. Base: `b784d02787908e36f78c9e0a3007870995fa79ba`
(PR #1 integrata).

## Struttura e ambito

Rimossi da Git i cinque moduli duplicati in `build/lib/tiff_viewer/`, i sei
file in `tiff_viewer.egg-info/` e i quattro file bytecode nelle cache Python.
Il nuovo `.gitignore` esclude build, distribuzioni, metadati generati, cache
e ambienti virtuali, compresi `.venv` e `.venv-windows` usati dagli installer.
Setuptools cerca esplicitamente nella radice solo `tiff_viewer` e i suoi
eventuali sottopacchetti ordinari, senza scoprire namespace impliciti.

I cinque moduli applicativi, i test scientifici, le dipendenze dichiarate,
Python >=3.10, la versione 1.0.0 e il GUI entry point restano invariati.
Non servono più aggiornamenti manuali di una seconda copia del codice.
La nota `contrast-sampling-validation.md` descrive la verifica storica della
PR #1: la sincronizzazione manuale lì citata è superata da questa pulizia.

`.gitignore` impedisce di aggiungere artefatti accidentalmente, ma non cancella
eventuali cache già presenti sul disco. Per distribuire usare sempre una
copia pulita del repository. La build isolation dei backend isola gli strumenti
Python, non garantisce la pulizia di una vecchia directory `build/`.

## Verifiche effettivamente eseguite

Ambiente Linux x86_64, Python 3.12.14, pip 26.2.2, setuptools 84.1.0,
wheel 0.48.0, NumPy 2.3.5 e Pillow 12.3.0.

L'accesso Git diretto non era disponibile: i 33 file della base sono stati
recuperati dall'integrazione GitHub, con hash Git di ciascun blob verificato
rispetto alla base. Dopo la pulizia, `git archive` del commit locale ha creato
una nuova directory contenente solo i file versionati, senza build, egg-info,
bytecode o ambienti virtuali.

- Suite esistente sui sorgenti: `python -m unittest discover -s tests -v`,
  **18 test superati**.
- Wheel dalla copia pulita tramite
  `python -m pip wheel --no-deps --no-build-isolation --wheel-dir ../direct-wheel .`:
  **costruito correttamente** (`tiff_viewer-1.0.0-py3-none-any.whl`).
- Distribuzione sorgente tramite
  `python -c "from setuptools import build_meta; build_meta.build_sdist('../sdist')"`;
  estrazione in una nuova directory e seconda costruzione con `pip wheel`
  e gli stessi flag: **superate**. La sdist non contiene `build/` o bytecode;
  i metadati egg-info rigenerati nella sdist sono normali e non sono versionati.
- Entrambi i wheel contengono esattamente i cinque moduli Python attesi,
  identici byte per byte ai sorgenti, senza test, build, egg-info o bytecode.
- Installazione effettiva del wheel diretto con `pip install --no-deps`
  in un nuovo venv creato con `--system-site-packages`: **superata**.
  NumPy e Pillow provengono dall'ambiente ospite; questo non costituisce una
  verifica con dipendenze completamente isolate.
- Suite esistente eseguita da `/tmp` con il Python del venv e
  `-I -m unittest discover -s /percorso/assoluto/copia-pulita/tests -v`:
  **18 test superati sul pacchetto installato**. Verificato che `__file__`
  del modulo punti al `site-packages` del nuovo venv, esterno ai sorgenti.
- Tutti i moduli installati coincidono con quelli nei due wheel e nei sorgenti.
  SHA256 di `image_processing.py`:
  `01a377b8c04a816bc6de4645c378b4121c9dafe3b9a9b3bb4405fe1837f7c6e7`.
  Sul pacchetto installato, l'immagine float32 1500×1000 con valori 10 nei
  primi due terzi e 1000 nell'ultimo terzo restituisce `(10.0, 1000.0)`.
- Metadati verificati: Python >=3.10; `numpy>=1.26`, `Pillow>=10.0`,
  `tifffile>=2024.2.12`; `gui_scripts` uguale a
  `tiff-viewer = tiff_viewer.app:main`. Launcher Linux generato e presente,
  senza eseguirlo.

## Limiti e verifica completa da ripetere

L'indice accessibile nell'ambiente non fornisce `build` e `tifffile`.
Non è stato possibile completare `python -m build` con backend isolato né
l'installazione con tutte le dipendenze. I wheel sono stati costruiti usando
il backend setuptools già installato, non simulando o sostituendo tifffile.

Su una macchina con accesso alle dipendenze, partire da un nuovo checkout del
branch della PR. Creare un venv per la build, attivarlo, quindi eseguire:

```bash
python -m pip install build
python -m build
```

Creare un secondo venv **senza** `--system-site-packages` e installarvi il
wheel con tutte le dipendenze:

```bash
python -m pip install /percorso/assoluto/checkout/dist/tiff_viewer-1.0.0-py3-none-any.whl
python -m pip check
```

Spostarsi fuori dal checkout, usando sempre il Python del secondo venv:

```bash
python -I -c "import tiff_viewer.image_processing as m; print(m.__file__)"
python -I -m unittest discover -s /percorso/assoluto/checkout/tests -v
python -I -m tiff_viewer
```

Su Windows usare percorsi Windows e il Python in `Scripts`; su Linux usare
quello in `bin`. Ripetere su entrambe le piattaforme e con Python 3.10,
oltre alla versione normalmente usata. Verificare l'apertura di un TIFF reale,
il launcher e gli installer. Non sono stati eseguiti test GUI, prove Windows,
una matrice Python o benchmark; questa PR non cambia il comportamento scientifico.
