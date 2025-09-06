"""
Простой HTTP сервер для обработки команд бота как альтернатива WebSocket
"""
import logging
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from bot_commands import command_handler
from config import config

logger = logging.getLogger(__name__)

class BotWebhookHandler(BaseHTTPRequestHandler):
    """Обработчик HTTP запросов для команд бота"""
    
    def do_POST(self):
        """Обработка POST запросов от Mattermost"""
        try:
            # Читаем данные запроса
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # Парсим JSON
            data = json.loads(post_data.decode('utf-8'))
            
            # Извлекаем информацию о сообщении
            text = data.get('text', '').strip()
            user_email = data.get('user_email', '')
            channel_id = data.get('channel_id', '')
            team_id = data.get('team_id', '')
            user_id = data.get('user_id', '')
            
            # Определяем тип канала
            channel_type = 'D' if data.get('channel_name', '').startswith('@') else 'O'
            
            if text and user_email:
                # Обрабатываем команду
                response = command_handler.handle_message(
                    text, user_email, channel_type, channel_id, team_id, user_id
                )
                
                if response:
                    # Отправляем ответ
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    
                    response_data = {
                        'text': response,
                        'response_type': 'in_channel'
                    }
                    
                    self.wfile.write(json.dumps(response_data).encode('utf-8'))
                    logger.info(f"Обработана команда от {user_email}: {text[:50]}...")
                else:
                    self.send_response(200)
                    self.end_headers()
            else:
                self.send_response(400)
                self.end_headers()
                
        except Exception as e:
            logger.error(f"Ошибка обработки webhook: {e}")
            self.send_response(500)
            self.end_headers()
    
    def do_GET(self):
        """Обработка GET запросов - статус сервера"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            status = {
                'status': 'ok',
                'service': 'mattermost-bot-webhook',
                'version': '1.0.0'
            }
            
            self.wfile.write(json.dumps(status).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Отключаем стандартные логи HTTP сервера"""
        pass

class WebhookServer:
    """Простой HTTP сервер для webhook"""
    
    def __init__(self, port=None):
        self.port = port or config.WEBHOOK_PORT
        self.server = None
        self.thread = None
        
    def start(self):
        """Запуск сервера в отдельном потоке"""
        try:
            self.server = HTTPServer(('', self.port), BotWebhookHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"🌐 Webhook сервер запущен на порту {self.port}")
            logger.info(f"📡 Endpoint для команд: http://localhost:{self.port}/")
            logger.info(f"💚 Health check: http://localhost:{self.port}/health")
        except Exception as e:
            logger.error(f"Ошибка запуска webhook сервера: {e}")
    
    def stop(self):
        """Остановка сервера"""
        if self.server:
            self.server.shutdown()
            logger.info("🛑 Webhook сервер остановлен")

# Глобальный экземпляр сервера
webhook_server = WebhookServer()
