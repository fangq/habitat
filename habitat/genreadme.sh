#!/bin/sh

cat habitat/habitatdb/i18n/lang.en | awk '/<<HOMEPAGE_DEFAULT/{doprint=1;}; \
/^HOMEPAGE_DEFAULT/{doprint=0;} \
/.*/ {if(doprint==2) print; if(doprint==1) doprint=2;}' > README.txt

cat habitat/habitatdb/i18n/lang.cn | awk '/<<HOMEPAGE_DEFAULT/{doprint=1;}; \
/^HOMEPAGE_DEFAULT/{doprint=0;} \
/.*/ {if(doprint==2) print; if(doprint==1) doprint=2;}' > README_Chinese.txt

