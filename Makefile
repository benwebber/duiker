.PHONY: all \
        build \
        build-release \
        dist \
        clean \
        install \
        setup

ifeq ($(shell $(CC) -dM -E -x c /dev/null | grep -c __clang__), 1)
CFLAGS = -DSQLITE_DISABLE_INTRINSIC
endif

PACKAGE := $(shell cargo read-manifest | jq -r .name)
VERSION := $(shell cargo read-manifest | jq -r .version)
TARGET  := $(shell rustc -Vv | awk '/host/ { print $$2 }')

all: build

dist: build-release
	mkdir -p dist/
	tar -C target/release -czvf dist/$(PACKAGE)-$(VERSION)-$(TARGET).tar.gz $(PACKAGE)

build:
	CFLAGS=$(CFLAGS) cargo build

build-release:
	CFLAGS=$(CFLAGS) cargo build --release

clean:
	cargo clean
	$(RM) -r dist/

install:
	cargo install --path .

setup:
	cargo install --no-default-features --features sqlite diesel_cli
