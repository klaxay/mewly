PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: install run run-offline test
install:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install -r requirements.txt

run:
	$(VENV_PYTHON) -m uvicorn server:app --ws-max-size 96000 --ws-max-queue 1

run-offline:
	TRANSCRIBER=dummy ASSISTANT=dummy $(MAKE) run

test:
	$(VENV_PYTHON) -m pytest -q
