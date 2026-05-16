#!/bin/sh

serverid=$(ps aux | grep "python.*http.server" | grep -v 'grep'|awk '{print $2}')

if [ ! -z $serverid ]
then
        kill -9 $serverid
fi
