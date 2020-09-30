#!/bin/sh


source ./config.sh

$OUT_DB_PSQL << _EOF_


drop table if exists raw_files cascade;

create table raw_files
(
	file_id	    text,
	name		text,
	create_timestamp	double precision,
	create_user	text,
	size		bigint
);

truncate raw_files;

\echo importing raw files

\copy raw_files(file_id, name, create_timestamp, create_user, size) from 'data/files.csv';

\echo creating files index
create index raw_file_id on raw_files(file_id);




_EOF_
