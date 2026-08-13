# Yamaguchi Lean 4 Library publishing data

This directory is the source of truth for the personal homepage and the
shared `YamaLean4Lib_pages/` documentation site:

- `homepage.json` and `homepage.css`: Japanese and English homepage content
  and style
- `libraries.json`: the ordered public-library catalog and the location of
  each library's publishing metadata
- `libraries/<id>/release.json`: repository, pinned commit, version, toolchain,
  and generation timestamp for one independently published Lean library
- `libraries/<id>/modules.json`: the audited module inventory for that library
- `libraries/<id>/export.json`: the optional workspace-to-project export
  contract for that library
- `assets/`: the established Lean documentation UI

The sibling `generator/` reads these files and generates one shared
documentation tree. Lean source remains in independent sibling Git projects,
one per registered library id (for example, `ProCGroups/`).

Publishing data and generator sources are versioned with the website but are
not copied into the GitHub Pages artifact.
