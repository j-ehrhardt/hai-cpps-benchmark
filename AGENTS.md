# Documentation branch guide

This is the `gh-pages` branch for the HAI-CPPS v2.2 website. Keep documentation changes here. The current simulation code is on `dev_v2.2_debug` and will be merged into `v2.2` and `main` manually by the user.

- Edit `_sources/**/*.txt` for page content. `docs/build.py` converts those files into Sphinx sources and rebuilds the root HTML.
- Keep `README.md`, `docs/requirements.txt`, and the built pages in sync with the editable sources. Preserve `.nojekyll`.
- Verify claims against `dev_v2.2_debug`, especially `code/campaign.py`, `code/campaign_plan.py`, `code/dataset_io.py`, `code/diagnosis_export.py`, `code/benchmark_setup.json`, and `models/`.
- The full v2.2 campaign has 160 healthy and 190 fault recordings. It has persistent and temporary fault variants, separate measurement/command/oracle tables, and an internal actuator event audit.
- Treat `oracle_states.parquet`, fault labels, timing metadata, spill diagnostics, and both audit files as offline or validation data, not online model inputs.
- Build with `python docs/build.py` and review the diff for stale links or v2.0 instructions. Commit site changes only on `gh-pages`. Do not modify simulation branches when updating the site.
