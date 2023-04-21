import logging
import os
import sys
import time

import requests
import telegram

from dotenv import load_dotenv
from http import HTTPStatus
from typing import Union

from exceptions import HTTPRequestError

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
    """отправляет сообщение в Telegram чат."""
    try:
        logging.info(f'Бот отправил сообщение {message}')
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug('Сообщение успешно отправлено')
    except Exception as error:
        logging.error(error)


def get_api_answer(current_timestamp: int) -> Union[dict, str]:
    """создает и отправляет запрос к эндпоинту."""
    params = {'from_date': current_timestamp}
    logging.info(f'Отправка запроса на {ENDPOINT} с параметрами {params}')
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.exceptions.RequestException as exc:
        logging.error(f"Проблема с подключением к эндпоинту {ENDPOINT}")
        raise exc
    if response.status_code != HTTPStatus.OK:
        logging.error(
            f"Эндпоинт {ENDPOINT} недоступен."
            f"Код ответа API: {response.status_code}"
        )
        raise HTTPRequestError("Код ответа от API не 200.")
    return response.json()


def check_response(response: dict):
    """Проверяет ответ API на корректность и соответствует ожиданиям."""
    if not isinstance(response, dict):
        raise TypeError("Ответ не словарь")
    logging.info("Получаем homeworks")

    homeworks = response.get("homeworks")

    if homeworks is None:
        raise KeyError("Не нашли homeworks в ответе")
    if not isinstance(homeworks, list):
        raise TypeError("homeworks не список")
    if not homeworks:
        logging.info("Не найдены homeworks")

    return homeworks


def parse_status(homework: dict) -> str:
    """Извлекает из информации и статус конкретной домашней работы."""
    homework_name = homework.get("homework_name")
    homework_status = homework.get("status")

    if homework_name is None:
        raise KeyError("Не нашли homework_name в homework")
    if homework_status is None:
        raise KeyError("Не нашли status в homework")

    verdict = HOMEWORK_VERDICTS.get(homework_status)
    if verdict is None:
        raise KeyError(
            f"Недокументированный статус {homework_name}"
            " домашней работы в ответе API"
        )

    logging.info(f"Получили новый статус {homework_name} - {verdict}")
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
        format='%(asctime)s [%(levelname)s] %(message)s',
        stream=sys.stdout

    )
    main()
