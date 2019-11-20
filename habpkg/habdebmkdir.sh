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

ROOTDIR=debian
CGIDIR=$ROOTDIR/var/lib/$PKGNAME/script
DATADIR=$ROOTDIR/var/lib/$PKGNAME/data
DOCDIR=$ROOTDIR/usr/share/doc/$PKGNAME
I18NDIR=$ROOTDIR/usr/share/locale
BINDIR=$ROOTDIR/usr/bin
MENUDIR=$ROOTDIR/usr/share/applications
ICONDIR=$ROOTDIR/usr/share/pixmaps
   
mkdir -p $CGIDIR
mkdir -p $DATADIR
mkdir -p $DOCDIR
mkdir -p $ROOTDIR/DEBIAN/
mkdir -p $BINDIR

for fn in *.desktop; do
   mkdir -p $MENUDIR; break;
done

if [ -d pixmap ]; then
   mkdir -p $ICONDIR
fi

chmod -s -R $ROOTDIR
