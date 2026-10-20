# NetSy / MASS-GT comparison

`main.pdf` is the short presentation (default Beamer layout, official Catppuccin Latte palette, Teal accent).
The slides deliberately distinguish fixed-input stage comparisons, independently synthesized runs, bug fixes, and new modelling assumptions.

Rebuild from the saved comparison artifacts:

```sh
PYTHONPATH=src .venv/bin/python presentation/build.py
cd presentation
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The plotting script additionally needs matplotlib; model installation does not.
See `../validation/README.md` and `../validation/results/` for methods, numbers, source revisions and limitations. The slides contain no claim of empirical validation for a new fleet or study case.
