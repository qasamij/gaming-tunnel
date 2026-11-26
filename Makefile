.PHONY: test compile clean

test:
	python3 -m unittest discover -s tests -t . -v

compile:
	python3 -m compileall -q src

clean:
	python3 -m compileall -q -f -x '^$$' src >/dev/null 2>&1 || true
	find . -type d -name __pycache__ -exec rm -rf {} +
