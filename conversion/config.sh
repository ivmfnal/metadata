IN_DB_PSQL="psql -h sampgsdb03.fnal.gov -p 5435 -U samread -d sam_dune_prd"
OUT_DB_PSQL="psql -h ifdb02.fnal.gov -d metadata"


function preload_meta() {

    input=$1

    source ./config.sh

    $OUT_DB_PSQL << _EOF_

    create temp table meta_csv (
    	file_id	text,
    	name	text,
    	value	text
    );

    \echo imporing data ...

    \copy meta_csv(file_id, name, value) from '${input}';

    \echo inserting ...

    insert into meta (file_id, meta)
    (
        select f.file_id, jsonb_build_object(m.name, m.value)
            from meta_csv m, raw_files f
            where f.file_id = m.file_id
    );

_EOF_

}
