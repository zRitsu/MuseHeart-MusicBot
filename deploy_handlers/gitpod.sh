cp -n .env-example .env
python -m venv venv
source venv/bin/activate
pip install -U poetry
pip install -r requirements.txt
