import logging
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

logging.basicConfig(
    level=logging.DEBUG,
    stream=stdout,
    format='%(asctime)s, %(levelname)s, %(message)s'
)


def check_tokens():
    """Проверка доступности переменных окружения."""
    if PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        return True
    return False


def send_message(bot, message):
    """Отправка сообщения в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception:
        raise telegram.error.TelegramError(
            'сбой при отправке сообщения в Telegram'
        )
    logging.debug('Удачная отправка сообщения в Telegram')


def get_api_answer(timestamp):
    """Запрос к API-сервису."""
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except Exception:
        raise EndpointAccessException('сбой при запросе к эндпоинту')
    response_content = response.json()
    if response.status_code != HTTPStatus.OK:
        raise EndpointAccessException(f'сбой при запросе к эндпоинту - '
                                      f'{response_content["code"]}')
    return response_content


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    if not isinstance(response, dict):
        raise TypeError(
            ('ошибка в ответе API - неверный тип данных для '
             'ответа (ожидался словарь)')
        )
    if not (('homeworks' in response) and ('current_date' in response)):
        raise AnswerApiException(
            ('ошибка в ответе API - '
             'отсутствует ожидаемый ключ в ответе')
        )
    if not isinstance(response['homeworks'], list):
        raise TypeError(
            ('ошибка в ответе API - неверный тип данных для '
             'значения ключа "homeworks"')
        )


def parse_status(homework):
    """Извлечение статуса из информации о конкретной домашней работе."""
    if not (('status' in homework) and ('homework_name' in homework)):
        raise KeyError(
            ('ошибка при парсинге информации о домашней работе '
             '- отсутствует ключ в словаре')
        )
    if homework['status'] not in HOMEWORK_VERDICTS:
        raise AnswerParsingException(
            ('ошибка при парсинге информации о домашней работе '
             '- неожиданный статус домашней работы')
        )

    verdict = HOMEWORK_VERDICTS[homework['status']]
    homework_name = homework['homework_name']
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Отсутствует обязательная переменная окружения')
        return

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            if len(response['homeworks']) == 0:
                logging.debug('В ответе отсутствуют новые статусы')
            for homework in response['homeworks']:
                send_message(bot, parse_status(homework))
            timestamp = response['current_date']
            last_error_message = ''
        except telegram.error.TelegramError as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if last_error_message != message:
                last_error_message = message
                send_message(bot, message)

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
