PYTHON ?= python3

.PHONY: docs docs-sync docs-lint docs-test docs-status

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
