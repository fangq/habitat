#!/bin/sh

serverid=$(ps aux | grep "python webserv.py" | grep -v 'grep'|awk '{print $2}')               

if [ ! -z $serverid ] 
then
        kill -9 $serverid
fi
