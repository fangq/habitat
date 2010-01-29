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

if [ $# -ne 1 ]; then
     echo 1>&2 Usage: $0 package-name
     exit 2
fi

PKGNAME=$1

CGIDIR=debian/var/lib/$PKGNAME/script
DATADIR=debian/var/lib/$PKGNAME/data
DOCDIR=debian/usr/share/doc/$PKGNAME
I18NDIR=debian/usr/share/locale
BINDIR=debian/usr/bin
MENUDIR=debian/usr/share/applications
ICONDIR=debian/usr/share/pixmaps
   
mkdir -p $CGIDIR
mkdir -p $DATADIR
mkdir -p $DOCDIR
mkdir -p debian/DEBIAN/
mkdir -p $BINDIR

for fn in *.desktop; do
   mkdir -p $MENUDIR; break;
done

if [ -d pixmap ]; then
   mkdir -p $ICONDIR
fi
