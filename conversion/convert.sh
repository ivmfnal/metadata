#!/bin/bash

rm  data/*.csv

echo --- loading users ...
time ./load_users.sh

echo --- loading raw files ...
time ./load_files.sh

echo --- preloading attributes ...
time ./preload_attrs.sh

echo --- preload runs/subruns ...
time ./preload_runs_subruns.sh

echo --- splitting lbne_data.detector_type values into lists ...
time ./preload_detector_type.sh

echo --- splitting DUNE_data.detector_config values into lists ...
time ./preload_detector_config.sh

echo --- preloading file types ...
time ./preload_file_types.sh

echo --- preloading file formats ...
time ./preload_formats.sh

echo --- preloading run types ...
time ./preload_run_types.sh

echo --- preloading data tiers ...
time ./preload_data_tiers.sh

echo --- preloading app families ...
time ./preload_app_families.sh

echo --- preloading data streams ...
time ./preload_data_streams.sh

echo --- loading lineages ...
time ./load_lineages.sh

echo --- merging data into the files table ...
time ./merge_meta.sh

echo --- building indexes ...
time ./build_indexes.sh

echo --- creating other tables ...
time ./create_other_tables.sh

echo --- building foreign keys ...
time ./build_foreign_keys.sh




