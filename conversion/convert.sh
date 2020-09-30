#!/bin/bash

rm  data/*.csv

echo --- loading users ...
./load_users.sh

echo --- loading raw files ...
./load_files.sh

echo --- preloading attributes ...
./preload_attrs.sh

echo --- preload runs/subruns ...
./preload_runs_subruns.sh

echo --- splitting lbne.detector_type values into lists ...
./preload_detector_type.sh

echo --- preloading file types ...
./preload_file_types.sh

echo --- preloading file formats ...
./preload_formats.sh

echo --- preloading run types ...
./preload_run_types.sh

echo --- preloading data tiers ...
./preload_data_tiers.sh

echo --- preloading app families ...
./preload_app_families.sh

echo --- preloading data streams ...
./preload_data_streams.sh

echo --- loading lineages ...
./load_lineages.sh

echo --- merging data into the files table ...
./merge_meta.sh

echo --- building indexes ...
./build_indexes.sh

echo --- creating other tables ...
./create_other_tables.sh

echo --- building foreign keys ...
./build_foreign_keys.sh




