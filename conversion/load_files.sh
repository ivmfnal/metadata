#!/bin/sh

psql -h ifdb02.fnal.gov ivm \
	<< _EOF_


drop table raw_files cascade;
drop table files cascade;

create table raw_files
(
	id	text,
	name		text,
	create_timestamp	double precision,
	create_user	text,
	size		bigint
);

truncate raw_files;

\echo importing raw files

\copy raw_files(id, name, create_timestamp, create_user, size) from 'data/files.csv';

\echo creating files index
create index raw_file_id on raw_files(id);

create table files
(
	id	text,
	namespace	text,
	name		text,
	create_user	text,
	create_timestamp	timestamp with time zone,
	size		bigint,
	metadata	jsonb
);


_EOF_
