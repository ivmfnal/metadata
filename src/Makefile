FILES = trees.py dbobjects2.py mql9.py grammar9.py filters.py py3.py signed_token.py

build:	$(LIBDIR)
	cp $(FILES) $(LIBDIR)
	echo 'Version="$(VERSION)"' > $(LIBDIR)/Version.py
	
$(LIBDIR):
	mkdir -p $@
