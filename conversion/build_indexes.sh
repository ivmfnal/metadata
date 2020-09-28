#!/bin/sh

source ./config.sh

$OUT_DB_PSQL << _EOF_

create index files_datasets_file_id on files_datasets(file_id);
create unique index files_names on files(namespace, name);
create index files_meta_index on files using gin (metadata);
create index files_meta_index on files using gin (metadata jsonb_path_ops);



_EOF_
