ANALIZZATORE SUPERENALOTTO

Questo progetto crea una piccola app Streamlit che:
- scarica lo storico delle estrazioni SuperEnalotto dal web;
- calcola i numeri più frequenti;
- calcola i numeri ritardatari;
- segnala i numeri che non escono da almeno 5 anni;
- mostra una "probabilità teorica reale" (sempre uguale per tutti i numeri: 6,67%);
- mostra un "indice statistico %" costruito su ritardo e frequenza storica.

IMPORTANTE
L'indice statistico NON è una vera probabilità matematica di uscita.
In un'estrazione casuale ogni numero mantiene la stessa probabilità teorica di essere nella sestina successiva.

COME USARLO
1) Installa Python 3.10+.
2) Installa i pacchetti:
   pip install streamlit pandas requests beautifulsoup4 lxml html5lib
3) Avvia l'app:
  py -m streamlit run superenalotto_analyzer.py
4) Premi il pulsante "Aggiorna dati e analizza".

FILE
- superenalotto_analyzer.py -> app principale
- README_superenalotto.txt -> istruzioni

NOTE TECNICHE
- Lo script usa come sorgente web l'archivio storico per anno.
- Se il sito cambia struttura HTML, il parser potrebbe richiedere un piccolo aggiornamento.
