FILES = __init__.py filters.py
DBFILES = __init__.py dbobjects2.py
MQLFILES = __init__.py grammar9.py mql9.py trees.py
UTILFILES = __init__.py py3.py rfc2617.py signed_token.py 

MODULEDIR=$(LIBDIR)/metacat

build:
	mkdir -p $(MODULEDIR) $(MODULEDIR)/db $(MODULEDIR)/mql $(MODULEDIR)/util
	cp $(FILES) $(MODULEDIR)
	cd db; cp $(DBFILES) $(MODULEDIR)/db
	cd mql; cp $(MQLFILES) $(MODULEDIR)/mql
	cd util; cp $(UTILFILES) $(MODULEDIR)/util
	echo 'Version="$(VERSION)"' > $(MODULEDIR)/Version.py
	cd $(LIBDIR); ln -s metacat/Version.py .
	
