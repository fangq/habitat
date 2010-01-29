############################################################
#               Habitat Packaging Makefile
#
#  Author: Qianqian Fang <fangq at nmr.mgh.harvard.edu>
#  History:
#      2010/01/28   modified from wqy packaging scripts
############################################################

PKGNAME=habitat-wiki
VERSION=0.2.0

deb: i18n
	-habpkg/habdebmkdir.sh $(PKGNAME)
	-habpkg/habdebcopy.sh  $(PKGNAME) $(VERSION)
	-dpkg -b debian $(PKGNAME)-$(VERSION).deb
rpm: i18n
	# empty
i18n:
	@for lang in i18n/*;\
	do\
	   if [ -f $$lang/$(PKGNAME).po ]; then\
		msgfmt -o $$lang/$(PKGNAME).mo $$lang/$(PKGNAME).po;\
	   fi;\
	done
clean:
	-rm -rf debian rpmroot pkg.info $(PKGNAME)-$(VERSION).deb $(PKGNAME)-$(VERSION)*.rpm
