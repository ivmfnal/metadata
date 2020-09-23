#!/bin/sh

psql -q -h sampgsdb03.fnal.gov -p 5435 -U samread sam_dune_prd \
	> ./data/file_types.csv \
	<< _EOF_

create temp view active_files as
        select * from data_files
                where retired_date is null;

copy (
	select f.file_id, 'SAM.file_type', 's', null, null, ft.file_type_desc
		from active_files f, file_types ft
		where f.file_type_id = ft.file_type_id
) to stdout;



_EOF_
