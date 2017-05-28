.PHONY: all \
	clean \
    debug \
	install \
	setup

all: debug

clean:
	cargo clean

debug:
	CFLAGS=-DSQLITE-DISABLE_INTRINSIC=1 cargo build

install:
	cargo install --path .

setup:
	cargo install --no-default-features --features sqlite diesel_cli
