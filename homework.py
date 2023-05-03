import logging
import os
import time
from http import HTTPStatus
from typing import Union

import requests
import telegram
from dotenv import load_dotenv

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
    except telegram.error.TelegramError as error:
        logging.error(error)
        return False


def get_api_answer(current_timestamp: int) -> Union[dict, str]:
    """Создает и отправляет запрос к эндпоинту."""
    parameters = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': current_timestamp})
    logging.info(
        f'Отправка запроса на {ENDPOINT} '
        f'с параметрами {parameters["params"]} '
        f'и загаловками {HEADERS}'
    )
    try:
        response = requests.get(**parameters)
    except requests.exceptions.RequestException:
        raise ConnectionError(
            f'Ошибка подключения: '
            f'Невозможно подключиться к {ENDPOINT} '
            f'параметры: {parameters["params"]}, '
            f'заголовки: {HEADERS}'
        )
    if response.status_code != HTTPStatus.OK:
        error_message = (
            f'Ошибка HTTP {response.status_code}: {response.reason}\n'
            f'{response.text}'
        )

        raise HTTPRequestError(error_message)
    return response.json()


def check_response(response: dict):
    """Проверяет ответ API на корректность и соответствует ожиданиям."""
    if not isinstance(response, dict):
        raise TypeError('Ответ не словарь')
    logging.info('Получаем homeworks')

    homeworks = response.get('homeworks')

    if not homeworks:
        raise EmptyResponseFromAPI('Список homeworks пуст')
    if not isinstance(homeworks, list):
        raise TypeError('homeworks не список')
    return homeworks


def parse_status(homework: dict) -> str:
    """Извлекает из информации статус конкретной домашней работы."""
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')

    if not homework_name:
        raise KeyError('Не нашли homework_name в homework')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            f'Неожиданное значение статуса "{homework_status}"'
            f'для работы "{homework_name}"'
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
    if not check_tokens():
        logging.critical(
            'Отсутствует обязательная переменная окружения.\n'
            'Программа принудительно остановлена.'
        )
        raise KeyError('Отсутствует обязательная переменная окружения.')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = 0
    prev_report = {}
    current_report = {
        'homework_name': None,
        'status': None
    }
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks:
                current_report['homework_name'] = homeworks[0]['homework_name']
                current_report['status'] = homeworks[0]['status']
                message = parse_status(current_report)
                current_report['status'] = message
            else:
                message = 'Нет новых статусов'
                current_report['status'] = message
            if current_report != prev_report:
                if send_message(bot, message):
                    prev_report = current_report.copy()
                    current_timestamp = response.get('current_date', 0)
            else:
                logging.info('Статусы не изменились')
        except EmptyResponseFromAPI as error:
            logging.error(error)
        except Exception as error:
            current_report['status'] = f'Сбой в работе программы: {error}'
            logging.error(f'Произошла ошибка: {current_report.get("status")},'
                          f'{error}')
            if current_report != prev_report:
                send_message(bot, current_report['status'])
                prev_report = current_report.copy()
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(__file__ + '.log', encoding='UTF-8')],
        format=('%(asctime)s [%(levelname)s]'
                '%(funcName)s:%(lineno)d %(message)s'),
    )
    main()
