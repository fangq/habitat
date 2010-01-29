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

CGIDIR=debian/var/lib/$PKGNAME/script
DATADIR=debian/var/lib/$PKGNAME/data
DOCDIR=debian/usr/share/doc/$PKGNAME
I18NDIR=debian/usr/share/locale
BINDIR=debian/usr/bin
MENUDIR=debian/usr/share/applications
ICONDIR=debian/usr/share/pixmaps

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

for fn in *.desktop; do
   cp -a *.desktop $MENUDIR; break;
done

if [ -d pixmap ]; then
    mkdir -p $ICONDIR
    cp -a pixmap/* $ICONDIR
fi

[ -d debsrc ] && cp -a debsrc/* debian/DEBIAN/
sed -i "s/%NAME%/$PKGNAME/g"  debian/DEBIAN/*
sed -i "s/%VERSION%/$VERSION/g"  debian/DEBIAN/*

awk '/\# What is Habitat/{dop=1;} /^$/{if(dop>0) dop++;} /./{if(dop==2) print " " $0;}' README.txt >> debian/DEBIAN/control

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
