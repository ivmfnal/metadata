#!/bin/sh

source ./config.sh

$OUT_DB_PSQL << _EOF_
alter table parent_child add foreign key (parent_id) references files(file_id);
alter table parent_child add foreign key (child_id) references files(file_id);

alter table files add foreign key(creator)      references users(username);
alter table files add foreign key(namespace)    references namespaces(name);

_EOF_

