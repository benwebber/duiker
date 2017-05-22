.PHONY: all \
	clean \
	dist \
	help \
	install \
	pyz \
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
	-find . -name '*.egg-info' -execdir rm -rf {} \;
	-find . -name '__pycache__' -execdir rm -rf {} \;
	find . -name '*.egg' -delete
	find . -name '*.pyc' -delete

dist: sdist wheel pyz

install:
	python setup.py install

pyz: clean
	-find . -name '*.egg-info' -execdir rm -rf {} \;
	./script/mkpyz dist/duiker

release: dist
	twine upload dist/*.whl dist/*.tar.gz

sdist: clean
	python setup.py sdist

wheel: clean
	python setup.py bdist_wheel
