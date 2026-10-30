.PHONY: all clean test
all:
	$(MAKE) -C src
	ln -sf src/client client
	ln -sf src/server server
clean:
	$(MAKE) -C src clean
	$(RM) client server
test: all
	python3 tests/test_local.py
