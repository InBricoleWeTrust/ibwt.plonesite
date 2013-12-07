#!/usr/bin/env bash
PROJECT="ibwt.ibwt.plonesite"
IMPORT_URL="git@gitorious-git.makina-corpus.net/"
cd $(dirname $0)/..
[[ ! -d t ]] && mkdir t
rm -rf t/*
tar xzvf $(ls -1t ~/cgwb/$PROJECT*z|head -n1) -C t
files="
./
"
for f in $files;do
    rsync -aKzv t/$PROJECT/$f $f
done
# vim:set et sts=4 ts=4 tw=80: 
