.PHONY: all \
	clean \
    debug \
	install \
	setup

ifeq ($(shell $(CC) -dM -E -x c /dev/null | grep -c __clang__), 1)
CFLAGS = -DSQLITE_DISABLE_INTRINSIC
endif

all: debug

clean:
	cargo clean

debug:
	CFLAGS=$(CFLAGS) cargo build

install:
	cargo install --path .

release:
	CFLAGS=$(CFLAGS) cargo build --release

setup:
	cargo install --no-default-features --features sqlite diesel_cli
