.PHONY: all install test run cli clean docker-build

all: install test

install:
	pip install -e .

test:
	python3 -m unittest discover -s tests

run:
	python3 main.py

cli:
	python3 -m src.cli -i

docker-build:
	docker build -t zasi:5.0.0 .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf *.egg-info build dist
