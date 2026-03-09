.PHONY: dev test lint

dev:
	pip install -e ./rb-container[dev]

test:
	pytest ./rb-container

lint:
	black ./rb-container
