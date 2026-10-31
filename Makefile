.PHONY: all clean test
all:
	$(MAKE) -C src
	ln -sf src/client client
	ln -sf src/server server
clean:
	$(MAKE) -C src clean
	$(RM) client server
test: all
	python3 tests/test_protocol.py
	python3 tests/test_transport.py
	python3 tests/test_probes.py
	python3 tests/test_openflow.py
	python3 tests/test_controller.py
	python3 tests/test_metrics.py
	python3 tests/test_local.py
