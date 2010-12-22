CC = gcc
CFLAGS = -Wall -O3 -D_GNU_SOURCE
LDFLAGS = -lncurses -lpthread
OBJECTS = ssterm.o 
PROGNAME = ssterm
BINDIR = /usr/local/bin

all: $(PROGNAME)

install: $(PROGNAME)
	install -m 0755 $(PROGNAME) $(BINDIR)

$(PROGNAME): $(OBJECTS)
	$(CC) $(LDFLAGS) -o $@ $(OBJECTS) 

clean:
	rm -rf $(PROGNAME) *.o

uninstall:
	rm -f $(BINDIR)/$(PROGNAME)

