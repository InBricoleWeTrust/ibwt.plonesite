#!/usr/bin/env bash
PRODUCTNAME='ibwt.plonesite'
I18NDOMAIN=$PRODUCTNAME
CWD=$(dirname $0)
cd ${CWD}
for d in  ../../../.. ../..;do
    if [[ -d "${d}/bin" ]];then
        export PATH="${d}/bin:${PATH}"
    fi
done
i18ndude=$(which i18ndude)
echo "Using ${i18ndude} in ${CWD}"
# Synchronise the .pot with the templates.
${i18ndude} rebuild-pot --pot locales/${PRODUCTNAME}.pot --merge locales/${PRODUCTNAME}-manual.pot --create ${I18NDOMAIN} .
# Synchronise the resulting .pot with the .po files
for po in locales/*/LC_MESSAGES/${PRODUCTNAME}.po;do
    ${i18ndude} sync --pot locales/${PRODUCTNAME}.pot $po
done
