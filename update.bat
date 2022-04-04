cd "%~dp"
git reset --hard && git pull --allow-unrelated-histories -X theirs && pip3 install -r requirements.txt --force-reinstall
