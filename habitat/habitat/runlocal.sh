#!/bin/sh

CGIDIR=`dirname $0`
mkdir -p $CGIDIR/cgi-bin
cp -a $CGIDIR/index.cgi $CGIDIR/cgi-bin/index.cgi
chmod +x $CGIDIR/cgi-bin/index.cgi

serverid=$(ps aux | grep "python .*webserv.py" | grep -v 'grep'|awk '{print $2}')

if [ ! -z $serverid ]
then
        kill -9 $serverid
fi

cd $CGIDIR
python $CGIDIR/webserv.py &
#WEBSERVPID=$!
#echo $WEBSERVPID > /var/lock/wiki2server.pid

mybrowser="$(which firefox || which epiphany|| which konqueror ||which opera || which arora)"
echo "$mybrowser"

$mybrowser "http://localhost:51712/cgi-bin/index.cgi"
