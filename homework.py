import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv
from http import HTTPStatus
from typing import Union

from exceptions import HTTPRequestError, EmptyResponseFromAPI

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
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


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в Telegram чат."""
    logging.info(f'Попытка отправки сообщения {message}')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug('Сообщение успешно отправлено')
        return True
    except Exception as error:
        logging.error(error)
        return False


def get_api_answer(current_timestamp: int) -> Union[dict, str]:
    """Создает и отправляет запрос к эндпоинту."""
    parameters = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': current_timestamp})
    try:
        response = requests.get(**parameters)
    except requests.exceptions.RequestException as exc:
        raise ConnectionError(f'Ошибка подключения: {exc}')
    if response.status_code != HTTPStatus.OK:
        raise HTTPRequestError('Код ответа от API не 200.')
    return response.json()


def check_response(response: dict):
    """Проверяет ответ API на корректность и соответствует ожиданиям."""
    if not isinstance(response, dict):
        raise TypeError('Ответ не словарь')
    logging.info('Получаем homeworks')

    homeworks = response.get('homeworks')

    if homeworks is None:
        raise EmptyResponseFromAPI('Список homeworks пуст')
    if not isinstance(homeworks, list):
        raise TypeError('homeworks не список')
    return homeworks


def parse_status(homework: dict) -> str:
    """Извлекает из информации и статус конкретной домашней работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if not homework_name:
        raise KeyError('Не нашли homework_name в homework')
    if homework_status not in HOMEWORK_VERDICTS:
        raise KeyError(
            f'Недокументированный статус {homework_name}'
            ' домашней работы в ответе API'
        )

    verdict = HOMEWORK_VERDICTS[homework_status]
    logging.info(f'Получили новый статус {homework_name} - {verdict}')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения необходимых для работы."""
    list_env = [
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ]
    return all(list_env)


def main():
    """Основная логика работы бота."""
    last_send = {
        'error': None,
    }
    if not check_tokens():
        logging.critical(
            'Отсутствует обязательная переменная окружения.\n'
            'Программа принудительно остановлена.'
        )
        sys.exit('Отсутствует обязательная переменная окружения.')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            for homework in homeworks:
                message = parse_status(homework)
                if last_send.get(homework['homework_name']) != message:
                    send_message(bot, message)
                    last_send[homework['homework_name']] = message
            current_timestamp = response.get('current_date')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if last_send['error'] != message:
                send_message(bot, message)
                last_send['error'] = message
        else:
            last_send['error'] = None
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        filename='program.log',
        format=('%(asctime)s [%(levelname)s]'
                '%(funcName)s:%(lineno)d %(message)s'),
        stream=sys.stdout

    )
    main()
