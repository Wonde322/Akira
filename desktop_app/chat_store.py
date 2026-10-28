"""Private desktop transcripts, separate from long-term agent memory."""
import json
import os
from pathlib import Path
from uuid import uuid4


class ChatStore:
    def __init__(self, path=None):
        from config import RUNTIME_DIR
        self.path = Path(path) if path else RUNTIME_DIR / 'desktop_chats.json'
        self.chats = []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            for chat in data.get('chats', []):
                if isinstance(chat, dict) and isinstance(chat.get('id'), str) and isinstance(chat.get('messages'), list):
                    chat['messages'] = [m for m in chat['messages'] if isinstance(m, dict) and m.get('role') in ('user', 'akira') and isinstance(m.get('text'), str)]
                    self.chats.append(chat)
            self.active = data.get('active')
        except (OSError, ValueError, TypeError, AttributeError):
            self.active = None
        if not self.chats:
            self.create()
        if self.active not in {c['id'] for c in self.chats}:
            self.active = self.chats[0]['id']

    def create(self):
        chat = {'id': 'desktop-' + uuid4().hex, 'title': 'Новый чат', 'messages': []}
        self.chats.append(chat)
        self.active = chat['id']
        self.save()
        return chat

    def delete(self, chat_id):
        self.chats = [chat for chat in self.chats if chat['id'] != chat_id]
        if not self.chats:
            self.create()
        elif self.active == chat_id:
            self.active = self.chats[0]['id']
        self.save()

    def get(self, chat_id=None):
        return next(c for c in self.chats if c['id'] == (chat_id or self.active))

    def append(self, text, role, chat_id=None, context=None):
        chat = self.get(chat_id)
        message = {'text': str(text), 'role': role}
        if context is not None:
            message['context'] = str(context)
        chat['messages'].append(message)
        if role == 'user' and chat['title'] == 'Новый чат':
            chat['title'] = ' '.join(str(text).split())[:48]
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'active': self.active, 'chats': self.chats}, stream, ensure_ascii=False)
        temporary.replace(self.path)
