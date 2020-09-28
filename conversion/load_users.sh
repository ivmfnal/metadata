#!/bin/sh

source ./config.sh

$OUT_DB_PSQL << _EOF_

drop table users cascade;

create table users
(
    username    text    primary key,
    name        text,
    email       text,
    flags       text
);


\copy users (username, name, email) from 'data/users.csv';

insert into users(username, name, flags)
	values('admin','Admin user', 'a');





_EOF_
