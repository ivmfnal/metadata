#!/bin/sh

psql -q -h sampgsdb03.fnal.gov -p 5435 -U samread sam_dune_prd \
	> ./data/run_types.csv \
	<< _EOF_

create temp view active_files as
        select * from data_files
                where retired_date is null;

copy (
	select distinct df.file_id as file_id, 'SAM.run_type', 's', null, null, rt.run_type
                        from active_files df
                                inner join data_files_runs dfr on dfr.file_id=df.file_id
                                inner join runs r on r.run_id=dfr.run_id
                                inner join run_types rt on rt.run_type_id = r.run_type_id
			where rt.run_type is not null
			order by df.file_id
) to stdout;



_EOF_
