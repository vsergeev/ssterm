PREFIX=/usr
BINDIR=$(PREFIX)/bin

all:

install:
	install -D -m 0755 ssterm.py $(DESTDIR)$(BINDIR)/ssterm

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/ssterm

