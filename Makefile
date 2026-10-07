PY := .venv/bin/python
JUPYTER := .venv/bin/jupyter

.PHONY: setup data dataset test report pdf

setup:            ## create venv and install dependencies
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

data:             ## download BTS monthly files into data/raw/ (default 2024-01..2025-12)
	$(PY) scripts/download_bts.py

dataset:          ## clean data/raw/ into data/processed/flights.parquet
	$(PY) scripts/build_dataset.py

test:
	.venv/bin/pytest -q

report:           ## execute the analysis notebook and export a code-free HTML report + figures
	cd notebooks && ../$(JUPYTER) nbconvert --to html --no-input --execute 02_analysis.ipynb \
		--output-dir ../report --output aviation_delay_report

CHROME ?= $(firstword $(wildcard /opt/pw-browsers/chromium-*/chrome-linux/chrome) chromium google-chrome)

pdf: report       ## print the HTML report to PDF with headless Chrome (override CHROME=... if needed)
	$(CHROME) --headless --no-sandbox --disable-gpu --no-pdf-header-footer \
		--print-to-pdf=report/aviation_delay_report.pdf report/aviation_delay_report.html
