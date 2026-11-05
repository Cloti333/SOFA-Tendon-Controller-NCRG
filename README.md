# Tendon-Controller-RM-NCRG

Scena base SOFA per il progetto motore–molla–tubo.

## Avvio

Frecce su/giù: caricano e scaricano il motore (0,35 mm per tasto); `k`: passa tra le tre rigidezze della molla; `0`: reset.

La lunghezza complessiva a riposo è 100 mm: 20 mm di molla + 20 mm di albero rigido + 60 mm di tratto flessibile. Il tubo Nitinol (80 mm) è modellato con una mesh tetraedrica volumetrica e `TetrahedronFEMForceField`, seguendo l'architettura dell'esempio 4 (`ElasticMaterialObject` STLIB). La superficie visiva e quella di collisione sono mappate sul volume FEM. I primi 20 mm del tubo sono bloccati; i 60 mm distali sono flessibili. La mesh corrente usa 15 divisioni assiali, 2 attraverso lo spessore e 8 circonferenziali: 384 nodi e 1.440 tetraedri.

`mesh/tube_tetra.vtu` e `mesh/tube_surface.obj` sono le mesh del tubo.

Il controllo è manuale: le frecce su/giù variano la corsa a passi di 0,35 mm; `k` cicla tra le rigidezze 0,6, 1,2 e 4,8 N/mm; `0` azzera l'attuazione. Lo smorzamento della molla è calcolato dalla variazione di allungamento tra i passi. La tensione del tendine è limitata a 10 N, l'allungamento a 15 mm e la variazione di tensione a 5 N/s. L'isteresi seleziona i moduli di carico/scarico del Nitinol (77/65 GPa).
