#!/bin/sh

source ./config.sh

echo dumping data ...

$IN_DB_PSQL -q \
	> ./data/app_families.csv \
	<< _EOF_

create temp view active_files as
        select * from data_files
                where retired_date is null;

create temp table attrs
(
	file_id	bigint,
	name text,
	value text
);

insert into attrs(file_id, name, value)
(
	select f.file_id, 'SAM.application.version', a.version
	from active_files f, application_families a where a.appl_family_id = f.appl_family_id
);

insert into attrs(file_id, name, value)
(
	select f.file_id, 'SAM.application.family', a.family
	from active_files f, application_families a where a.appl_family_id = f.appl_family_id
);

insert into attrs(file_id, name, value)
(
	select f.file_id, 'SAM.application.name', a.appl_name
	from active_files f, application_families a where a.appl_family_id = f.appl_family_id
);

insert into attrs(file_id, name, value)
(
	select f.file_id, 'SAM.application', a.family || '.' || a.appl_name
	from active_files f, application_families a where a.appl_family_id = f.appl_family_id
);


copy (
	select file_id, name, value
		from attrs
		order by file_id
) to stdout;
_EOF_

echo dumped `wc -l ./data/app_families.csv` records
echo loading data ...

$OUT_DB_PSQL << _EOF_

create temp table app_families (
	file_id	text,
	name	text,
	value	text
);

\copy app_families(file_id, name, value) from 'data/app_families.csv';

create index af_file_id on app_families(file_id);

insert into meta (file_id, meta)
(
	select f.file_id, jsonb_object_agg(a.name, a.value)
		from app_families a, raw_files f
        where f.file_id = a.file_id
        group by f.file_id
);

_EOF_
