#!/bin/bash

# Uzstāda webhook, lai Telegram zina, kur sūtīt atbildes
python3 -c 'import asyncio; from kvn import set_webhook; asyncio.run(set_webhook())'

# Palaiž Gunicorn ar Flask aplikāciju (flask_app)
exec gunicorn --bind 0.0.0.0:5000 kvn:flask_app
