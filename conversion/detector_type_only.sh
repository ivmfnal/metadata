#!/bin/sh

source ./config.sh

$IN_DB_PSQL -q \
	> ./data/detector_type_lists.csv \
	<< _EOF_

create temp view active_files as
        select * from data_files
                where retired_date is null;


create temp view string_attrs as
    select f.file_id as file_id, pc.param_category || '.' || pt.param_type as name, pv.param_value as value
                                from active_files f
                                inner join data_files_param_values dfv on f.file_id = dfv.file_id
                                inner join param_values pv on pv.param_value_id = dfv.param_value_id
                                inner join param_types pt on pt.param_type_id = dfv.param_type_id
                                inner join data_types dt on dt.data_type_id = pt.data_type_id
                                inner join param_categories pc on pc.param_category_id = pt.param_category_id
                                where dt.data_type = 'string'
;

copy ( 
    select file_id, regexp_split_to_array(value, ':')
        from string_attrs
        where name = 'lbne_data.detector_type'
    ) to stdout;
_EOF_

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


$OUT_DB_PSQL << _EOF_

create temp table detector_type_lists (
    file_id text,
    value text[]
);

\copy detector_type_lists(file_id, value) from 'data/detector_type_lists.csv';

create temp view detector_type_as_json_list as
	select file_id, jsonb_object_agg('lbne_data.detector_type', value) as obj
		from detector_type_lists
		group by file_id
;


create table meta (
	file_id text,
	meta	jsonb
);

\echo building meta ...

insert into meta (file_id, meta)
(
	select r.file_id, 
        coalesce(d.obj, '{}')::jsonb
		from raw_files r
			left outer join detector_type_as_json_list d on d.file_id = r.file_id
);

_EOF_