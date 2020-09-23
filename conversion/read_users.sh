#!/bin/sh

psql -h sampgsdb03.fnal.gov -p 5435 -U samread sam_dune_prd \
	> ./data/users.csv \
	<< _EOF_

copy (	select username, first_name || ' ' ||  last_name, email_address
	from persons
) to stdout



_EOF_

