# Makefile for the open-source release of adventure 2.5

# SPDX-FileCopyrightText: (C) Eric S. Raymond <esr@thyrsus.com>
# SPDX-License-Identifier: BSD-2-Clause

# To build with save/resume disabled, pass CFLAGS="-DADVENT_NOSAVE"
# To build with auto-save/resume enabled, pass CFLAGS="-DADVENT_AUTOSAVE"

PREFIX      ?= /usr/local
BINDIR      ?= $(PREFIX)/bin
DATADIR     ?= $(PREFIX)/share
MANDIR      ?= $(DATADIR)/man

VERSION=$(shell sed -n <NEWS.adoc '/^[0-9]/s/:.*//p' | head -1)

CC?=gcc
CCFLAGS+=-std=c99 -Wall -Wextra -Werror -D_DEFAULT_SOURCE -DVERSION=\"$(VERSION)\" -O2 -D_FORTIFY_SOURCE=2 -fstack-protector-all $(CFLAGS) -g $(EXTRA)
LIBS=$(shell pkg-config --libs libedit)
INC+=$(shell pkg-config --cflags libedit)

# LLVM/Clang on macOS seems to need -ledit flag for linking
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LIBS += -ledit
endif

OBJS=main.o init.o actions.o score.o misc.o saveresume.o
CHEAT_OBJS=cheat.o init.o actions.o score.o misc.o saveresume.o
SOURCES=$(OBJS:.o=.c) advent.h adventure.yaml Makefile control make_dungeon.py templates/*.tpl

# Rules

# Note: to suppress the footers with timestamps being generated in HTML,
# we use "-a nofooter".
# To debug asciidoc problems, you may need to run "xmllint --nonet --noout --valid"
# on the intermediate XML that throws an error.
.SUFFIXES: .html .adoc .6

.adoc.6:
	asciidoctor -D. -a nofooter -b manpage $<
.adoc.html:
	asciidoctor -D. -a nofooter -a webfonts! $<

.c.o:
	$(CC) $(CCFLAGS) $(INC) $(DBX) -c $<

.PHONY: all html clean cppcheck pylint check spellcheck reflow coverage
.PHONY: version dist release refresh linty debug

# Build

all: advent

advent:	$(OBJS) dungeon.o
	$(CC) $(CCFLAGS) $(DBX) -o advent $(OBJS) dungeon.o $(LDFLAGS) $(LIBS)

main.o:	 	advent.h dungeon.h
init.o:	 	advent.h dungeon.h
actions.o:	advent.h dungeon.h
score.o:	advent.h dungeon.h
misc.o:		advent.h dungeon.h
cheat.o:	advent.h dungeon.h
saveresume.o:	advent.h dungeon.h

dungeon.o:	dungeon.c dungeon.h
	$(CC) $(CCFLAGS) $(DBX) -c dungeon.c

dungeon.c dungeon.h: make_dungeon.py adventure.yaml advent.h templates/*.tpl
	./make_dungeon.py

cheat: $(CHEAT_OBJS) dungeon.o
	$(CC) $(CCFLAGS) $(DBX) -o cheat $(CHEAT_OBJS) dungeon.o $(LDFLAGS) $(LIBS)

html: advent.html history.html hints.html

clean:
	rm -f *.o advent cheat *.html *.gcno *.gcda
	rm -f dungeon.c dungeon.h
	rm -f README advent.6 MANIFEST *.tar.gz
	rm -f *~
	rm -f .*~
	rm -rf coverage advent.info
	cd tests; $(MAKE) --quiet clean

# Validate

CSUPPRESSIONS = --suppress=checkersReport --suppress=missingInclude \
	--suppress=missingIncludeSystem --suppress=invalidscanf --suppress=unmatchedSuppression
cppcheck:
	@-cppcheck -I. --quiet --template=gcc -UOBJECT_SET_SEEN --enable=all $(CSUPPRESSIONS) *.[ch]

pylint:
	@-pylint --score=n *.py */*.py

check: advent cheat pylint cppcheck spellcheck
	@cd tests >/dev/null; $(MAKE) --quiet

spellcheck:
	@spellcheck adventure.yaml advent.adoc

reflow:
	@clang-format --style="{IndentWidth: 8, UseTab: ForIndentation}" -i $$(find . -name "*.[ch]")
	@black --quiet *.py

# Requires gcov, lcov, libasan6, and libubsan1
# The last two are Ubuntu names, might vary on other distributions.
# After this, run your browser on coverage/open-adventure/index.html
# to see coverage results. Browse coverage/adventure.yaml.html
# to see symbol coverage over the YAML file.
coverage: clean debug
	cd tests; $(MAKE) coverage --quiet

# Install/uninstall

install:
	install -d $(DESTDIR)$(BINDIR)
	install -m 755 advent $(DESTDIR)$(BINDIR)/advent
	install advent.1 $(DESTDIR)$(MANDIR)/man1/advent.1

uninstall:
	rm -f $(DESTDIR)$(BINDIR)/advent
	rm -f $(DESTDIR)$(MANDIR)/man1/advent.1

# Export

# README.adoc exists because that filename is magic on GitLab.
DOCS = COPYING NEWS.adoc README.adoc advent.adoc history.adoc notes.adoc hints.adoc advent.6 INSTALL.adoc
TESTFILES = tests/*.log tests/*.chk tests/README tests/decheck tests/Makefile
ALL = $(SOURCES) $(TOCS) $(TESTFILES)

advent-$(VERSION).tar.gz: $(ALL)
	mkdir advent-$(VERSION)
	cp -r $(ALL) advent-$(VERSION)
	tar -czf advent-$(VERSION).tar.gz advent-$(VERSION)
	rm -fr advent-$(VERSION)
	ls -l advent-$(VERSION).tar.gz

dist: advent-$(VERSION).tar.gz

release: advent-$(VERSION).tar.gz advent.html history.html hints.html notes.html
	shipper version=$(VERSION) | sh -e -x

refresh: advent.html notes.html history.html
	shipper -N -w version=$(VERSION) | sh -e -x

# Extra debugging productions

linty: CCFLAGS += -W
linty: CCFLAGS += -Wall
linty: CCFLAGS += -Wextra
linty: CCGLAGS += -Wpedantic
linty: CCFLAGS += -Wundef
linty: CCFLAGS += -Wstrict-prototypes
linty: CCFLAGS += -Wmissing-prototypes
linty: CCFLAGS += -Wmissing-declarations
linty: CCFLAGS += -Wshadow
linty: CCFLAGS += -Wnull-dereference
linty: CCFLAGS += -Wjump-misses-init
linty: CCFLAGS += -Wfloat-equal
linty: CCFLAGS += -Wcast-align
linty: CCFLAGS += -Wwrite-strings
linty: CCFLAGS += -Waggregate-return
linty: CCFLAGS += -Wcast-qual
linty: CCFLAGS += -Wswitch-enum
linty: CCFLAGS += -Wwrite-strings
linty: CCFLAGS += -Wunreachable-code
linty: CCFLAGS += -Winit-self
linty: CCFLAGS += -Wpointer-arith
linty: advent cheat

# These seem to be more modern options for enabling coverage testing.
# Documenting them here in case a future version bump disables --coverage.
#debug: CCFLAGS += -ftest-coverage
#debug: CCFLAGS += -fprofile-arcs

debug: CCFLAGS += -O0
debug: CCFLAGS += --coverage
debug: CCFLAGS += -ggdb
debug: CCFLAGS += -U_FORTIFY_SOURCE
debug: CCFLAGS += -fsanitize=address
debug: CCFLAGS += -fsanitize=undefined
debug: linty

# end
