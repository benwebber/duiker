.PHONY: all \
        build \
        build-release \
        clean \
        install \
        setup

ifeq ($(shell $(CC) -dM -E -x c /dev/null | grep -c __clang__), 1)
CFLAGS = -DSQLITE_DISABLE_INTRINSIC
endif

all: build

build:
	CFLAGS=$(CFLAGS) cargo build

build-release:
	CFLAGS=$(CFLAGS) cargo build --release

clean:
	cargo clean

install:
	cargo install --path .

setup:
	cargo install --no-default-features --features sqlite diesel_cli
