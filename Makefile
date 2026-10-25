.PHONY: install dev test lint format build installer clean

install:
	pip install -r requirements.txt

dev:
	pip install -r requirements-dev.txt

test:
	pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests

build:
	python -m PyInstaller FileCategorizer.spec --noconfirm --clean

installer: build
	ISCC FileCategorizer.iss

clean:
	rm -rf build dist .pytest_cache .ruff_cache
