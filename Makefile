PREFIX=/usr/local
BINDIR=$(PREFIX)/bin

install:
	install -D -m 0755 ssterm.py $(DESTDIR)$(BINDIR)/ssterm

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/ssterm

