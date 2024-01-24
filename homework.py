import logging
import logging.handlers
import os
import time
from http import HTTPStatus
from sys import stdout

import requests
import telegram
from dotenv import load_dotenv

from exceptions import AnswerApiException, AnswerParsingException
from exceptions import EndpointAccessException

load_dotenv()

PRACTICUM_TOKEN = os.getenv('TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    TOKENS = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID)
    )
    token_found = True
    for token_name, token in TOKENS:
        if not token:
            logging.critical(f'Отсутствует токен {token_name}')
            token_found = False

    if not token_found:
        raise NameError


def send_message(bot, message):
    """Отправка сообщения в Telegram чат."""
    logging.debug('Попытка отправки сообщения в Telegram')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError as error:
        logging.error(f'Cбой при отправке сообщения в Telegram: {error}')
        return False
    logging.debug(f'Cообщение в Telegram успешно отправлено: "{message}"')
    return True


def get_api_answer(timestamp):
    """Запрос к API-сервису."""
    request_args = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    logging.debug(
        'Попытка запроса к {url} с заголовком {headers} '
        'и параметрами {params}'.format(**request_args)
    )
    try:
        response = requests.get(**request_args)
    except requests.exceptions.RequestException:
        raise ConnectionError(
            'сбой при запросе к {url} с заголовком {headers} '
            'и параметрами {params}'.format(**request_args)
        )
    response_content = response.json()
    if response.status_code != HTTPStatus.OK:
        raise EndpointAccessException(
            f'сбой при запросе к эндпоинту {request_args["url"]}: '
            f'{response_content["code"]}, сервер ответил кодом '
            f'{response.status_code}'
        )
    return response_content


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            'ошибка в ответе API - неверный тип данных для '
            'ответа (ожидался словарь)'
        )
    if 'homeworks' not in response:
        raise AnswerApiException(
            'ошибка в ответе API - '
            'отсутствует ожидаемый ключ в ответе'
        )
    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(
            'ошибка в ответе API - неверный тип данных для '
            'значения ключа "homeworks"'
        )
    return homeworks


def parse_status(homework):
    """Извлечение статуса из информации о конкретной домашней работе."""
    if not (('status' in homework) and ('homework_name' in homework)):
        raise KeyError(
            'ошибка при парсинге информации о домашней работе '
            '- отсутствует ключ в словаре'
        )
    if homework['status'] not in HOMEWORK_VERDICTS:
        raise AnswerParsingException(
            'ошибка при парсинге информации о домашней работе '
            '- неожиданный статус домашней работы'
        )

    verdict = HOMEWORK_VERDICTS[homework['status']]
    homework_name = homework['homework_name']
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0
    last_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)
            if len(homeworks):
                homework = homeworks[0]
                message = parse_status(homework)
            else:
                message = 'В ответе отсутствуют новые статусы'
            if message != last_message:
                if send_message(bot, message):
                    last_message = message
                    timestamp = response.get('current_date')
            else:
                logging.debug('В ответе отсутствуют новые статусы')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.exception(message)
            if message != last_message:
                last_message = message
                send_message(bot, message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    stream_handler = logging.StreamHandler(stdout)
    file_handler = logging.FileHandler(f'{__file__}.log')
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[stream_handler, file_handler],
        format=(
            '%(asctime)s, %(levelname)s, %(message)s, %(funcName)s, %(lineno)s'
        )
    )
    main()
