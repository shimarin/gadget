BINDIR := $(HOME)/.local/bin

.PHONY: install
install:
	install -Dm755 gadget.py $(BINDIR)/gadget
