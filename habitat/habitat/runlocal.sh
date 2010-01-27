#!/bin/sh

mkdir -p cgi-bin
cp -a index.cgi cgi-bin/index.cgi
chmod +x cgi-bin/index.cgi

serverid=$(ps aux | grep "python webserv.py" | grep -v 'grep'|awk '{print $2}')

if [ ! -z $serverid ]
then
        kill -9 $serverid
fi

python webserv.py &
#WEBSERVPID=$!
#echo $WEBSERVPID > /var/lock/wiki2server.pid

mybrowser="$(which firefox || which epiphany|| which konqueror ||which opera || which arora)"
echo "$mybrowser"

$mybrowser "http://localhost:51712/cgi-bin/index.cgi"
