import argparse
import sqlite3
import sys
from pathlib import Path
from . import database, services
from .config import BOOKS_URL, database_path
from .models import DataError
from .validation import decimal_value, observation_time, timestamp


def quantity_arg(text):
    try:
        return decimal_value(text,'quantity',positive=True)
    except DataError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def integer_arg(text):
    try:
        value = int(text)
        if value < 0:
            raise ValueError()
        return value
    except ValueError:
        raise argparse.ArgumentTypeError('требуется целое неотрицательное число') from None


def pages_arg(text):
    value = integer_arg(text)
    if value == 0:
        raise argparse.ArgumentTypeError('число страниц должно быть положительным')
    return value


def time_arg(text):
    try:
        return observation_time(text)
    except DataError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser():
    parser = argparse.ArgumentParser(description='Анализ полной стоимости закупок',
        epilog='Глобальный --db указывается ПЕРЕД командой. demo всегда использует отдельную временную БД.')
    parser.add_argument('--db',type=Path,default=database_path(),help='SQLite; приоритет над PRICES_ANALYZER_DB')
    commands = parser.add_subparsers(dest='command',required=True)
    commands.add_parser('init-db',help='Создать SQLite без удаления данных')
    csv = commands.add_parser('import-csv',help='Импорт собственного CSV-формата')
    csv.add_argument('path',type=Path)
    csv.add_argument('--dry-run',action='store_true')
    collect = commands.add_parser('collect',help='Свежий HTTP-сбор учебного магазина')
    collect.add_argument('source',choices=['books'])
    collect.add_argument('--max-pages',type=pages_arg,default=1)
    collect.add_argument('--dry-run',action='store_true')
    html = commands.add_parser('import-html',help='Офлайн-разбор сохранённого HTML')
    html.add_argument('path',type=Path)
    html.add_argument('--observed-at',required=True,type=time_arg,help='Время снимка в ISO 8601 с часовым поясом')
    html.add_argument('--page-url',default=BOOKS_URL,help='Исходный URL страницы для относительных ссылок')
    html.add_argument('--dry-run',action='store_true')
    listing = commands.add_parser('list',help='Последние наблюдения')
    listing.add_argument('--product')
    listing.add_argument('--supplier')
    listing.add_argument('--source')
    history = commands.add_parser('history',help='История одного предложения')
    history.add_argument('--source',required=True)
    history.add_argument('--offer',required=True,help='Внешний ID предложения')
    compare = commands.add_parser('compare',help='Сравнить закупку')
    compare.add_argument('--product',required=True)
    compare.add_argument('--quantity',required=True,type=quantity_arg)
    compare.add_argument('--max-days',required=True,type=integer_arg)
    demo = commands.add_parser('demo',help='Полный офлайн-сценарий в отдельной временной БД')
    demo.add_argument('--directory',type=Path,help='Родительская папка временной demo-БД, по умолчанию backend/db')
    return parser


def shown(value):
    return 'неизвестно' if value is None else str(value)


def print_summary(result):
    if result.dry_run:
        print('DRY-RUN: ниже ожидаемый результат; SQLite не изменена.')
    print(f'Обработано: {result.processed}; добавлено: {result.added}; '
          f'пропущено как дубликаты: {result.duplicates}; отклонено: {len(result.errors)}')
    for error in result.errors:
        print(error,file=sys.stderr)
    return 1 if result.errors else 0


def print_observations(items):
    if not items:
        print('Наблюдения не найдены.')
    for item in items:
        offer = item.offer
        print(f'{offer.product.id} | {offer.product.name} | {offer.supplier.id}: {offer.supplier.name} | '
              f'{offer.source}/{offer.external_id}\n'
              f'  {item.price} {item.currency}/{offer.product.unit}; партия={shown(item.minimum_quantity)}; '
              f'доставка={shown(item.delivery_cost)}; доп.расходы={shown(item.extra_cost)}; '
              f'срок={shown(item.delivery_days)} дн.; наличие={shown(item.availability)}\n'
              f'  {timestamp(item.observed_at)} | {offer.url}')


def print_comparison(groups):
    if not groups:
        print('Данных недостаточно: надёжно выбрать лучший вариант нельзя.')
    for currency,unit,results in groups:
        print(f'Сопоставимая группа {currency}/{unit}:')
        for status,label in [('eligible','ДОПУСТИМЫЕ'),('incomplete','НЕПОЛНЫЕ'),('excluded','ИСКЛЮЧЁННЫЕ')]:
            matching = [r for r in results if r.status == status]
            if not matching:
                continue
            print(label)
            for result in matching:
                item = result.observation
                print(f'  {item.offer.supplier.name} [{item.offer.external_id}]: '
                      f'{item.price} × {result.quantity} = {result.subtotal}; '
                      f'доставка {shown(item.delivery_cost)}; доп.расходы {shown(item.extra_cost)}; '
                      f'итого {shown(result.total)} {currency}; партия {shown(item.minimum_quantity)}; '
                      f'срок {shown(item.delivery_days)} дн.'
                      + ('; ' + '; '.join(result.reasons) if result.reasons else ''))
        eligible = [r for r in results if r.status == 'eligible']
        if eligible:
            print(f'Минимум среди проверенных условий: {eligible[0].observation.offer.supplier.name}, {eligible[0].total} {currency}.')
        if not eligible or any(r.status == 'incomplete' for r in results):
            print('Данных недостаточно: надёжно выбрать лучший вариант среди всех предложений нельзя.')
    if len(groups) > 1:
        print('Валюты и единицы не конвертируются; общего победителя между группами нет.')


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == 'init-db':
            database.initialize(args.db)
            print(f'База готова: {args.db}')
        elif args.command == 'import-csv':
            return print_summary(services.import_csv(args.path,args.db,args.dry_run))
        elif args.command == 'import-html':
            print('Офлайн: сохранённый HTML, не свежий сетевой запрос.')
            return print_summary(services.import_html(args.path,args.db,args.observed_at,
                page_url=args.page_url,dry_run=args.dry_run))
        elif args.command == 'collect':
            print('Свежий HTTP-сбор Books to Scrape: учебные, не рыночные цены.')
            return print_summary(services.collect(args.db,args.max_pages,args.dry_run))
        elif args.command == 'list':
            print_observations(database.latest(args.db,product=args.product,supplier=args.supplier,source=args.source))
        elif args.command == 'history':
            print_observations(database.history(args.db,args.source,args.offer))
        elif args.command == 'compare':
            print_comparison(services.compare_purchase(args.db,args.product,args.quantity,args.max_days))
        elif args.command == 'demo':
            print('Офлайн-demo: отдельная временная БД, --db не используется; после сценария demo-БД удаляется.')
            result = services.demo(args.directory)
            for name in ('first','repeated','html'):
                print({'first':'Первый CSV-импорт','repeated':'Повторный CSV-импорт','html':'Сохранённый HTML'}[name])
                print_summary(result[name])
            print_observations(result['items'])
            print('История demo/paper-b:')
            print_observations(result['history'])
            print_comparison(result['comparisons'])
        return 0
    except (DataError, sqlite3.Error, OSError, UnicodeError) as exc:
        print(f'Ошибка: {exc}',file=sys.stderr)
        return 2
