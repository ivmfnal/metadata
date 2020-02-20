FILES = Server.py  filters.py rfc2617.py signed_token.py \
    base.html           dataset.html   login.html  named_queries.html  namespace.html   query.html      user.html \
    dataset_files.html  datasets.html  mql.html    named_query.html    namespaces.html  show_file.html  users.html



build:	$(SERVER_DIR)
	cp $(FILES) $(SERVER_DIR)
	mkdir -p $(SERVER_DIR)/static/js
	cp static/js/*.js $(SERVER_DIR)/static/js
	
$(SERVER_DIR):
	mkdir -p $@
