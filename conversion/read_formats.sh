#!/bin/sh

psql -q -h sampgsdb03.fnal.gov -p 5435 -U samread sam_dune_prd \
	> ./data/file_formats.csv \
	<< _EOF_

create temp view active_files as
        select * from data_files
                where retired_date is null;

copy (

	select f.file_id, 'SAM.file_format', 's', null, null, ff.file_format
		from active_files f, file_formats ff
		where f.file_format_id = ff.file_format_id
		order by f.file_id
) to stdout;



_EOF_
