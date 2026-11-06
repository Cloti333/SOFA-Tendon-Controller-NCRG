# Tendon-Controller-RM-NCRG

Scena base SOFA per il progetto motore–molla–tubo.

## Avvio

Frecce su/giù: caricano e scaricano il motore (0,35 mm per tasto); `0`: reset.

La lunghezza complessiva a riposo è 100 mm: 20 mm di molla + 20 mm di albero rigido + 60 mm di tratto flessibile. Il tubo Nitinol (80 mm) è modellato con una mesh tetraedrica volumetrica e `TetrahedronFEMForceField`, seguendo l'architettura dell'esempio 4 (`ElasticMaterialObject` STLIB). La superficie visiva e quella di collisione sono mappate sul volume FEM. I primi 20 mm del tubo sono bloccati; i 60 mm distali sono flessibili. La mesh corrente usa 15 divisioni assiali, 2 attraverso lo spessore e 8 circonferenziali: 384 nodi e 1.440 tetraedri.

`mesh/tube_tetra.vtu` e `mesh/tube_surface.obj` sono le mesh del tubo.

Il controllo è manuale: ogni pressione delle frecce su/giù sposta il motore di 0,35 mm senza limite superiore di corsa; `0` azzera l'attuazione. La rigidezza della molla è fissa a 1,2 N/mm. La tensione del tendine segue `T = k * DeltaLs ± isteresi`, senza limite superiore di forza. Il coefficiente di smorzamento nominale (1,5 N·s/mm) resta impostato nel `SpringForceField`. L'isteresi seleziona i moduli di carico/scarico del Nitinol (77/65 GPa).

All'avvio della scena si apre una finestra separata con cinque grafici aggiornati in tempo reale: traiettoria della punta `X-Y`, poi `DeltaY`, `u`, `T` e `DeltaLs` nel tempo. Nel grafico `X-Y`, la freccia su seleziona la curva blu continua per il carico; la freccia giù seleziona la curva magenta continua per lo scarico. Il colore resta associato alla fase selezionata finché non viene premuta l'altra freccia. I grafici temporali mostrano gli ultimi 30 secondi; la finestra si aggiorna ogni mezzo secondo e adatta automaticamente le scale ai dati. La scena scrive un campione a ogni passo in `dati_simulazione.csv` nella stessa cartella dello script; il file viene ricreato all'avvio della scena. `DeltaY` è riferito alla coordinata Y della punta al primo campione. Le colonne sono tempo (s), X/Y/DeltaY (mm), u (mm), T (N), DeltaLs (mm) e `fase_traiettoria` (1 carico, -1 scarico). Il visualizzatore usa Tkinter; per aprirlo manualmente: `python plot_live.py .\dati_simulazione.csv`.
