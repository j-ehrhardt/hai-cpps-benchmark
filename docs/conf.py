from datetime import datetime

project = "HAI-CPPS"
author = "Jonas Ehrhardt, Lukas Moddemann, Alexander Diedrich, Oliver Niggemann"
copyright = f"{datetime.now().year}, {author}"
release = "v2.2"

extensions = ["myst_parser"]
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
root_doc = "index"

html_theme = "sphinx_rtd_theme"
html_title = "HAI-CPPS v2.2 documentation"
html_logo = "_static/logo.png"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
html_js_files = ["js/current-year.js"]

myst_heading_anchors = 3
