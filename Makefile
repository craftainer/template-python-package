# The release contract release.yml drives -- see docs/TEMPLATE.md's
# "Release: a Makefile contract" section. This template itself ships no
# artifact, so every target is a documented no-op; an instance reimplements
# each target for its own artifact type (an OCI image, a package, a chart,
# ...) without needing to touch release.yml.

.PHONY: release-arches build sbom release-assets publish release-check finalize

# Prints (only) a JSON array of the arches to build on, once, first. Each
# arch then runs build/sbom/release-assets/publish natively on its own runner.
release-arches:
	@echo '["amd64"]'

build:
	@echo "template-base ships no artifact -- nothing to build."

sbom:
	@echo "template-base ships no artifact -- nothing to scan."

release-assets:
	@mkdir -p dist

publish:
	@echo "template-base ships no artifact -- nothing to publish."

# Runs once after every arch leg, inside the devcontainer with the stack up.
release-check:
	@echo "template-base ships no artifact -- nothing to check."

# Runs once after release-check, on the host runner (e.g. combine per-arch
# registry tags into a multi-arch manifest list).
finalize:
	@echo "template-base ships no artifact -- nothing to finalize."
