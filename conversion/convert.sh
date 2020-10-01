#!/bin/bash

rm  data/*.csv

echo
echo --- loading users ...
time ./load_users.sh

echo
echo --- loading raw files ...
time ./load_files.sh

echo
echo --- preloading attributes ...
time ./preload_attrs.sh

echo
echo --- preload runs/subruns ...
time ./preload_runs_subruns.sh

echo
echo --- splitting lbne_data.detector_type values into lists ...
time ./preload_detector_type.sh

echo
echo --- splitting DUNE_data.detector_config values into lists ...
time ./preload_detector_config.sh

echo
echo --- preloading file types ...
time ./preload_file_types.sh

echo
echo --- preloading file formats ...
time ./preload_formats.sh

echo
echo --- preloading run types ...
time ./preload_run_types.sh

echo
echo --- preloading data tiers ...
time ./preload_data_tiers.sh

echo
echo --- preloading app families ...
time ./preload_app_families.sh

echo
echo --- preloading data streams ...
time ./preload_data_streams.sh

echo
echo --- loading lineages ...
time ./load_lineages.sh

echo
echo --- merging metadata into the files table ...
time ./merge_meta.sh

echo
echo --- building indexes ...
time ./build_indexes.sh

echo
echo --- creating other tables ...
time ./create_other_tables.sh

echo
echo --- building foreign keys ...
time ./build_foreign_keys.sh




