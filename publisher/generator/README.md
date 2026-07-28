# Yamaguchi Lean 4 Library publisher

This reproducible publisher maintains the personal homepage and the complete
shared Lean documentation site at `YamaLean4Lib_pages/`.

```text
Github/
├── YamaLean4Lib/                  public website repository
│   ├── publisher/
│   │   ├── data/                 publishing data and static assets
│   │   └── generator/            generator, checkers, templates, and tests
│   └── YamaLean4Lib_pages/       generated shared documentation
└── ProCGroups/                    independent Lean source repository
```

Every Lean library has its own source repository and its own publishing record
under `publisher/data/libraries/<id>/`. The shared site presents all registered
libraries under the common title `Yamaguchi Lean 4 Library`; it does not create
or preserve a separate `<library>_pages/` site.

`update_repository.py --write` remains disabled because the legacy exporter
would overwrite the independent project's README. Source exports belong to
each library project.

## Release metadata

Preview, update, or check the ProCGroups release record against a clean checkout:

```sh
python3 stamp_release.py
python3 stamp_release.py --write
python3 stamp_release.py --check
```

The release records an exact source commit and derives its module inventory
from `Lean4/**/*.lean`.

## Website

Generate or verify the managed website:

```sh
python3 generate.py
python3 generate.py --check
python3 generate.py --repository-support-only
python3 tools/check_generated_site.py ../../YamaLean4Lib_pages
python3 tools/check_public_repository.py ../..
```

By default, each source checkout is a sibling of the website repository and is
named after its library id. For an explicit audit location, repeat
`--library-repository ID=PATH`. `--output` is accepted only for an exact public
repository clone with the configured GitHub origin.

The generator owns the public runtime files and `YamaLean4Lib_pages/`. It
preserves `.git/`, `LICENSE`, and `publisher/`; publisher sources are never
included in the deployed Pages artifact.

## Tests

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile generate.py build_site.py update_repository.py stamp_release.py
```
