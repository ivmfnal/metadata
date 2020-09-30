#!/bin/sh

source ./config.sh

$OUT_DB_PSQL << _EOF_

drop table if exists users cascade;

create table users
(
    username    text    primary key,
    name        text,
    email       text,
    flags       text    default ''
);


\copy users (username, name, email) from 'data/users.csv';

insert into users(username, name, flags)
	values('admin','Admin user', 'a');





_EOF_
