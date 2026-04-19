PYTHON ?= python3

.PHONY: dg ds dsj docs docs-sync docs-lint docs-test docs-status

dg: docs

ds: docs-status

dsj:
	$(PYTHON) tools/doc_workflow.py status --json

docs:
	$(PYTHON) tools/doc_workflow.py all

docs-sync:
	$(PYTHON) tools/doc_workflow.py sync

docs-lint:
	$(PYTHON) tools/doc_workflow.py lint

docs-test:
	$(PYTHON) tools/doc_workflow.py test

docs-status:
	$(PYTHON) tools/doc_workflow.py status
