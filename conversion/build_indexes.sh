#!/bin/sh

psql -h ifdb02.fnal.gov ivm \
	<< _EOF_

create unique index files_names on files(namespace, name);

alter table parent_child add foreign key (parent_id) references files(file_id);
alter table parent_child add foreign key (child_id) references files(file_id);

create index files_meta_index on files using gin (metadata);

_EOF_
