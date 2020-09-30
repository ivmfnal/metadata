#!/bin/bash

rm  data/*.csv

echo --- reading users ...
./read_users.sh

echo --- loading users ...
./load_users.sh

echo --- reading files ...
./read_files.sh

echo --- splitting lbne.detector_type ...
./split_detector_type.sh

echo --- reading file types ...
./read_file_types.sh
echo --- reading file formats ...
./read_formats.sh
echo --- reading run types ...
./read_run_types.sh
echo --- reading data tiers ...
./read_data_tiers.sh
echo --- reading app families ...
./read_app_families.sh

echo --- reading runs/subruns ...
./read_runs_subruns.sh

echo --- reading attributes ...
./read_attrs.sh

echo --- loading files ...
./load_files.sh

echo --- reading lineages ...
./read_lineages.sh

echo --- loading lineages ...
./load_lineages.sh


echo --- loading metdata ...
./load_meta.sh

echo --- building indexes ...
./build_indexes.sh

echo --- creating other tables ...
./create_other_tables.sh

echo --- building foreign keys ...
./build_foreign_keys.sh




