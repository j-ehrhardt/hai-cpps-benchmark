# HAI-CPPS v2.2 documentation

This branch contains the editable sources and published HTML for the [HAI-CPPS documentation website](https://j-ehrhardt.github.io/hai-cpps-benchmark/). The site describes the current simulation code on [`dev_v2.2_debug`](https://github.com/j-ehrhardt/hai-cpps-benchmark/tree/dev_v2.2_debug). The user will merge that branch into `v2.2` and `main` manually.

The v2.2 benchmark has ten topologies and a full campaign of **350 recordings**: 160 healthy and 190 single fault. It generates continuous, discrete, and hybrid Parquet measurements, separate controller commands, offline oracle data, and validation metadata. Start with the [site overview](https://j-ehrhardt.github.io/hai-cpps-benchmark/) or the [campaign output guide](https://j-ehrhardt.github.io/hai-cpps-benchmark/campaign-output.html).

## Edit and build this site

Edit the files in `_sources/` (the `.txt` suffix is removed by the builder). `docs/build.py` copies them into a temporary Sphinx source tree and writes the HTML into this branch. Site images and CSS are in `_static/` and `_images/`.

```bash
python -m pip install -r docs/requirements.txt
python docs/build.py
```

The builder treats Sphinx warnings as errors. After building, review the changed HTML and source files, then commit them on `gh-pages`. Keep code and model changes on `dev_v2.2_debug` until the user manually merges them.

The website documents the generator; it does not contain benchmark recordings. Use the [debug branch README](https://github.com/j-ehrhardt/hai-cpps-benchmark/blob/dev_v2.2_debug/README.md) for installation and campaign commands.
