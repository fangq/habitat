#!/bin/sh
############################################################
#              Habitat Debian Packaging Script
#
#  habdebmkdir.sh: script to create deb packaging folder structure
#
#  Author: Qianqian Fang <fangq at nmr.mgh.harvard.edu>
#  History:
#      2010/01/28    Initial version
#
############################################################

if [ $# -lt 2 ]; then
     echo 1>&2 Usage: $0 package-name version
     exit 2
fi

PKGNAME=$1
VERSION=$2

ROOTDIR=debian
CGIDIR=$ROOTDIR/var/lib/$PKGNAME/script
DATADIR=$ROOTDIR/var/lib/$PKGNAME/data
DOCDIR=$ROOTDIR/usr/share/doc/$PKGNAME
I18NDIR=$ROOTDIR/usr/share/locale
BINDIR=$ROOTDIR/usr/bin
MENUDIR=$ROOTDIR/usr/share/applications
ICONDIR=$ROOTDIR/usr/share/pixmaps

if [ ! -d $CGIDIR ]; then
     echo 1>&2 $CGIDIR does not exist, please run habdebmkdir.sh first
     exit 2
fi

if [ ! -d $DATADIR ]; then
     echo 1>&2 $DATADIR does not exist, please run habdebmkdir.sh first
     exit 2
fi

if [ ! -d $DOCDIR ]; then
     echo 1>&2 $DOCDIR does not exist, please run habdebmkdir.sh first
     exit 2
fi

cp -a *.txt $DOCDIR

#cp -a $PKGNAME/* $CGIDIR
cp -a habitat/* $CGIDIR

mv $CGIDIR/db $DATADIR
mv $CGIDIR/habitatdb $DATADIR

sed -i 's/"\.\/habitatdb"/"..\/data\/habitatdb"/' $CGIDIR/index.cgi
sed -i 's/dbname=db\/habitatdb\.db"/dbname=..\/data\/db\/habitatdb\.db"/' $DATADIR/habitatdb/config


for fn in *.desktop; do
   cp -a *.desktop $MENUDIR; break;
done

if [ -d pixmap ]; then
    mkdir -p $ICONDIR
    cp -a pixmap/* $ICONDIR
fi

[ -d debsrc ] && cp -a debsrc/* $ROOTDIR/DEBIAN/
sed -i "s/%NAME%/$PKGNAME/g"  $ROOTDIR/DEBIAN/*
sed -i "s/%VERSION%/$VERSION/g"  $ROOTDIR/DEBIAN/*

#sitekey=`perl -e 'print sprintf("%08X%08X",rand(0xFFFFFFFF),rand(0xFFFFFFFF))'`
#sed -i 's/^\(\s*\$CaptchaKey\s*=\s*.*\)/#\1\n\$CaptchaKey = 0;#HABSITEKEY#/' $DATADIR/habitatdb/config
#sed -i "s/0;#HABSITEKEY#/pack('H16','$sitekey');/" $DATADIR/habitatdb/config

#admpass=`perl -e "print crypt(sprintf('%08X',rand(0xFFFFFFFF)),'$sitekey')"`
#sed -i 's/^\(\s*\$AdminPass\s*=\s*.*\)/#\1\n\$AdminPass = 0;#HABADMPASS#/' $DATADIR/habitatdb/config
#sed -i "s/0;#HABADMPASS#/'$admpass';/" $DATADIR/habitatdb/config


echo " Habitat - a wiki and a portable content management system" >>$ROOTDIR/DEBIAN/control
awk '/\# What is Habitat/{dop=1;} /^$/{if(dop>0) dop++;} /./{if(dop==2) print " " $0;}' README.txt >> $ROOTDIR/DEBIAN/control

# install .mo files
if [ -d i18n ]; then
    for lang in `ls -1 i18n | sed -e 's/^i18n\///g'`
    do
	if [ -f i18n/$lang/*.mo ]; then
		mkdir -p $I18NDIR/$lang/LC_MESSAGES/; 
		cp -a i18n/$lang/*.mo $I18NDIR/$lang/LC_MESSAGES/
	fi
    done
fi

find $ROOTDIR/ -name ".svn"  | xargs rm -rf 
