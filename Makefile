# Perseus Multitext Viewer -- build orchestrator.
#
#   make               build every stale work (manifest-driven)
#   make work=tlg0085.tlg007   build just one work
#   make work=tlg0012          build every work in a textgroup (tlg0012.*)
#   make force         ignore the manifest, rebuild everything
#   make index         rebuild index.html only, from the existing monolith +
#                      web/ -- no ingestion. Use this after editing
#                      web/app.js, web/styles.css, or web/index_shell.html;
#                      those aren't TEI sources, so plain `make` never sees
#                      them as making a work stale, and `make force` would
#                      only pick the change up by re-ingesting everything.
#   make clean         delete the temp monolith (forces reconstitution
#                      from shards, or a full rebuild if shards are also gone)
#
# All the real logic lives in pipeline/build_all.py -- this is a thin
# wrapper so muscle-memory `make` still works.

PY := python3

.PHONY: build force index dashboard clean test

build:
	$(PY) -m pipeline.build_all $(if $(work),--work $(work))

force:
	$(PY) -m pipeline.build_all --force $(if $(work),--work $(work))

index:
	$(PY) -m pipeline.build_all --index-only

dashboard:
	$(PY) -m pipeline.word_dashboard
	$(PY) -m pipeline.build_all --index-only

clean:
	$(PY) -m pipeline.cleanup

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 $(PY) -m pytest tests/ -q
