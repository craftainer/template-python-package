# template-base

> [!NOTE]
> This repository is vibe coded with [Claude](https://claude.com/product/claude-code).

The generic "devcontainer + CI + AI-assisted workflow" scaffold shared by
a wider family of template repos — no application runtime, no backing
services, no language assumed. See [`docs/TEMPLATE.md`](docs/TEMPLATE.md)
for contents, getting started, checks, the release Makefile contract,
template sync, versions/config, and code style — everything about this
repository that's identical across every instance. A repo that wants a
full application skeleton on top of this (e.g. FastAPI/Postgres/Redis)
should instantiate that template instead — see
[`template-fastapi`](https://github.com/craftainer/template-fastapi),
itself an instance of this template.

Once instantiated, rename this file's title and description to the
actual project's; `docs/TEMPLATE.md` stays as-is and is what
`.github/workflows/template-sync.yml` keeps up to date.

## License

Licensed under the [GNU General Public License v3.0](LICENSE).
