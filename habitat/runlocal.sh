#!/bin/sh

CGIDIR=`dirname $0`
mkdir -p $CGIDIR/cgi-bin
cp -a $CGIDIR/index.cgi $CGIDIR/cgi-bin/index.cgi
chmod +x $CGIDIR/cgi-bin/index.cgi

$CGIDIR/stoplocal.sh

cd $CGIDIR
python3 -m http.server --cgi 51712 &

mybrowser="$(which google-chrome || which firefox|| which chromium-browser || which konqueror ||which opera)"
echo "$mybrowser"

$mybrowser "http://localhost:51712/cgi-bin/index.cgi"
