.PHONY: all \
	clean \
	dist \
	help \
	install \
	release \
	sdist \
	wheel

define USAGE
Targets:

  clean       remove build artifacts
  dist        build source distribution and wheel
  install     install package to active Python site packages
  release     build and upload package to PyPI
  sdist       build source distribution
  wheel       build wheel
endef

all: clean dist

help:
	@echo $(info $(USAGE))

clean:
	$(RM) -r build dist
	find . -name '*.egg' -delete
	find . -name '*.egg-info' -delete
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -delete

dist: sdist wheel

install:
	python setup.py install

release: dist
	twine upload dist/*.whl dist/*.tar.gz

sdist: clean
	python setup.py sdist

wheel: clean
	python setup.py bdist_wheel
