"""Small WSGI API. Use one Gunicorn process behind an HTTPS reverse proxy."""
import atexit
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from zippergen.telegram_notify import TelegramBotClient
from .service import Sessions, Gone, Unavailable


class API:
    def __init__(self, sessions, origins):
        self.sessions = sessions
        self.origins = frozenset(origins)
        if not self.origins:
            raise ValueError('Set at least one allowed website origin')
        for origin in self.origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
                raise ValueError('Origins must have a scheme and host, without a trailing slash')
            if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1'):
                raise ValueError('Public origins must use HTTPS')

    def __call__(self, env, start_response):
        origin = env.get('HTTP_ORIGIN', '')
        headers = [('Content-Type', 'application/json'), ('Cache-Control', 'no-store'),
                   ('X-Content-Type-Options', 'nosniff'), ('Vary', 'Origin')]
        if origin in self.origins:
            headers += [('Access-Control-Allow-Origin', origin),
                        ('Access-Control-Allow-Headers', 'Authorization, Content-Type'),
                        ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')]

        def reply(code, body):
            payload = json.dumps(body).encode()
            start_response(code, headers + [('Content-Length', str(len(payload)))])
            return [payload]

        method, path = env['REQUEST_METHOD'], env.get('PATH_INFO', '')
        if origin and origin not in self.origins:
            return reply('403 Forbidden', {'error': 'This website is not allowed.'})
        if method == 'OPTIONS':
            return reply('200 OK', {}) if origin in self.origins else reply('403 Forbidden', {})
        try:
            if method == 'GET' and path == '/api/config':
                return reply('200 OK', {'available': self.sessions.available(), 'lifetime_seconds': self.sessions.lifetime})
            if method == 'POST' and path == '/api/sessions':
                if origin not in self.origins:
                    return reply('403 Forbidden', {'error': 'Start the session from the demo website.'})
                if env.get('CONTENT_TYPE', '').split(';')[0] != 'application/json':
                    return reply('415 Unsupported Media Type', {'error': 'Expected JSON.'})
                try:
                    size = int(env.get('CONTENT_LENGTH') or '0')
                except ValueError:
                    return reply('400 Bad Request', {'error': 'Invalid request.'})
                if not 0 < size <= 64:
                    return reply('413 Content Too Large', {'error': 'Invalid request size.'})
                if json.loads(env['wsgi.input'].read(size)) != {}:
                    return reply('400 Bad Request', {'error': 'This demo uses a fixed example.'})
                source = env.get('REMOTE_ADDR', 'unknown')
                # Only the local reverse proxy may supply the real client address.
                if source in ('127.0.0.1', '::1'):
                    source = env.get('HTTP_X_REAL_IP', source)
                return reply('201 Created', self.sessions.create(source))
            if method == 'GET' and path == '/api/session':
                authorization = env.get('HTTP_AUTHORIZATION', '')
                if not authorization.startswith('Bearer '):
                    return reply('401 Unauthorized', {'error': 'A session token is required.'})
                return reply('200 OK', self.sessions.status(authorization[7:]))
            return reply('404 Not Found', {'error': 'Not found.'})
        except Gone:
            return reply('410 Gone', {'error': 'This demo session has expired or is no longer available.'})
        except Unavailable as exc:
            return reply('429 Too Many Requests', {'error': str(exc)})
        except (ValueError, UnicodeError):
            return reply('400 Bad Request', {'error': 'Invalid request.'})
        except Exception:
            # Never place credential-bearing upstream exceptions in HTTP responses or logs.
            logging.error('Demo API request failed. Check the service and private state directory.')
            return reply('503 Service Unavailable', {'error': 'The live demo is temporarily unavailable.'})


def create_app():
    os.umask(0o077)
    state = Path(os.environ.get('DEMO_STATE_DIR', '/var/lib/zippergen-demo'))
    # This service owns a separate site home and dedicated bot, not a user's existing deployment.
    os.environ.setdefault('ZIPPERGEN_HOME', str(state / 'site'))
    credentials = os.environ.get('CREDENTIALS_DIRECTORY')
    token_path = os.environ.get('DEMO_BOT_TOKEN_FILE') or (str(Path(credentials) / 'telegram-token') if credentials else '')
    if not token_path:
        raise RuntimeError('Provide the bot token through a private credential file')
    token = Path(token_path).read_text().strip()
    client = TelegramBotClient(token, timeout=10)
    try:
        bot = client.request('getMe')['result']
        if client.request('getWebhookInfo')['result'].get('url'):
            raise RuntimeError('This bot has a webhook. Use a dedicated demo bot without a webhook.')
    except Exception:
        raise RuntimeError('Cannot start the demo bot. Check its private credential and webhook configuration.') from None
    sessions = Sessions(state, client, bot['username'],
                        lifetime=int(os.environ.get('DEMO_SESSION_SECONDS', '1800')),
                        limit=int(os.environ.get('DEMO_MAX_SESSIONS', '12')),
                        starts_per_hour=int(os.environ.get('DEMO_MAX_STARTS_PER_IP_PER_HOUR', '5')))
    try:
        api = API(sessions, os.environ.get('DEMO_ORIGINS', '').split())
        sessions.start()
    except BaseException:
        sessions.close()
        raise
    atexit.register(sessions.close)
    return api
