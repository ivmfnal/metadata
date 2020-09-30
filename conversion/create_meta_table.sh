#/bin/bash

source config.sh

$OUT_DB_PSQL << _EOF_
create table if not exists meta
(
    file_id text,
    value   jsonb
);

truncate table meta;

_EOF_