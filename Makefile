.PHONY: test
test:
	pytest

package:
	python setup.py bdist_wheel --plat-name $(OS)

install:
	pip install .

.ONESHELL:
static-checks:
	black .
	flake8 .
	pylint ./rmount
	mypy rmount

publish: package
	twine upload dist/*.whl --verbose