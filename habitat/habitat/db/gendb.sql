create table page(
id varchar(512), version integer, 
author varchar(32),revision integer,tupdate integer,tcreate integer,
ip varchar(32),host varchar(64),summary varchar(128),text varchar(1024),
minor integer,newauthor integer,data varchar(32), tag varchar(32)
);

create index page_id on page(id ASC);

create table deletedpage(
id varchar(512), version integer,
author varchar(32),revision integer,tupdate integer,tcreate integer,
ip varchar(32),host varchar(64),summary varchar(128),text varchar(1024),
minor integer,newauthor integer,data varchar(32), tag varchar(32)
);

create index deletedpage_id on deletedpage(id ASC);


create table user(
id integer primary key autoincrement, name varchar(32) ,pass varchar(32),
randkey varchar(32),groupid varchar(32),lang varchar(8),
email varchar(64),param varchar(32),createtime integer,
stylesheet varchar(128),createip varchar(32),tzoffset integer,
pagecreate varchar(512),pagemodify varchar(512)
);

create table html(
id varchar(512) primary key,time integer,text varchar(1024)
);

create table rclog(
time integer, id varchar(512), summary  varchar(128),isedit integer,
host varchar(64),kind varchar(8),userid integer,name varchar(64),
revision integer,isadmin integer
);

create index rclog_time on rclog(time ASC);

create table system(
id varchar(32) primary key, data varchar(1024),time integer
);

create table lock(
id varchar(512) primary key, tag varchar(32), readcount integer, modcount integer, linkcount integer, note varchar(128)
);

create table watch(
page varchar(512), user varchar(32)
);

create index watch_page on watch(page ASC);

