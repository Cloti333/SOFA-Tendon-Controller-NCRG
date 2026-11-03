# Tendon-Controller-RM-NCRG

Scena base SOFA per il progetto motore–molla–tubo.

## Avvio

Dalla cartella `PROGETTO`:

```powershell
runSofa -l SofaPython3 .\Tendon-Controller-RM-NCRG\scena_motore_molla_tubo_base.py
```

Oppure dalla cartella SOFA `v26.06.00`:

```powershell
.\bin\runSofa.exe -l SofaPython3 .\PROGETTO\Tendon-Controller-RM-NCRG\scena_motore_molla_tubo_base.py
```

Frecce su/giù: carica e scarica il motore (0,35 mm per tasto); `1`: modalità autonoma; `0`: reset.

Le mesh usate dalla scena sono nella cartella `mesh`, accanto allo script. La forma a uncino è per ora resa con segmenti visuali orientabili; il modello FEM Nitinol con `CableConstraint` resta da integrare.
