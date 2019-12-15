FILES = dbobjects.py    mql5.py py3.py

build:	$(LIBDIR)
	cp $(FILES) $(LIBDIR)
	echo 'Version="$(VERSION)"' > $(LIBDIR)/Version.py
	
$(LIBDIR):
	mkdir -p $@
