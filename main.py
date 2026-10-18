"""CryptoSentinel command line. All supported modes execute virtual trades only."""
import argparse
import asyncio
from dataclasses import replace
import logging
import sys


def parser():
    result = argparse.ArgumentParser(description='CryptoSentinel - Binance public prices, virtual trades only')
    modes = result.add_mutually_exclusive_group()
    modes.add_argument('--demo', action='store_true', help='Offline synthetic full-cycle replay; separate account')
    modes.add_argument('--backtest', metavar='CSV', help='Historical OHLCV replay')
    modes.add_argument('--status', action='store_true', help='Show the persisted paper account without network')
    modes.add_argument('--check-live', action='store_true', help='Check real market data without opening new trades')
    result.add_argument('--once', action='store_true', help='One live analysis cycle, then exit')
    result.add_argument('--db', help='Explicit SQLite path; demo/backtest default to an in-memory account')
    result.add_argument('--symbol', default='BTC/USDT', help='Symbol for --backtest/--demo')
    result.add_argument('--report', help='Write a JSON replay report')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        from app.core.config import Settings
        settings = Settings.from_env()
        if args.db:
            settings = replace(settings, db_path=args.db)
        if args.demo or args.backtest:
            from app.backtesting.backtest_engine import demo_candles, load_data, run_backtest, save_report
            frame = demo_candles() if args.demo else load_data(args.backtest)
            mode = 'demo' if args.demo else 'backtest'
            report = run_backtest(frame, settings, args.symbol, args.db or ':memory:', mode)
            print('SENTETIK DEMO - strateji basarisi olcumu degildir.' if args.demo else 'TARIHSEL SANAL ISLEM TESTI')
            print(f'Mum: {report["rows"]} | Kapali islem: {report["closed_trades"]}')
            print(f'Baslangic: {report["initial_capital"]:.2f} | Son bakiye: {report["equity"]:.2f} USDT')
            print(f'Net PnL: {report["realized_net_pnl"]:+.2f} | Komisyon: {report["fees"]:.2f} USDT')
            print(f'Getiri: %{report["return_pct"]:.2f} | En buyuk dusus: %{report["max_drawdown_pct"]:.2f}')
            if args.report:
                save_report(report, args.report)
                print(f'Rapor: {args.report}')
        elif args.status:
            from app.core.database import DatabaseManager
            from app.services.reporting import format_report
            db = DatabaseManager(settings.db_path, settings.initial_capital)
            try:
                print(format_report(db))
                print('Acik pozisyonlar giris fiyatindan degerlendi; bu cevrimdisi bir durum raporudur.')
            finally:
                db.close()
        else:
            from app.trading.bot import CryptoSentinelBot
            # Diagnostic checks cannot send notifications and use a disposable account.
            if args.check_live:
                from app.core.database import DatabaseManager
                db = DatabaseManager(':memory:', settings.initial_capital, mode='check')
                settings = replace(settings, telegram_enabled=False)
                try:
                    report = asyncio.run(CryptoSentinelBot(settings, db).run(check=True))
                finally:
                    db.close()
            else:
                report = asyncio.run(CryptoSentinelBot(settings).run(once=args.once))
            if report:
                print(report)
        return 0
    except KeyboardInterrupt:
        print('\nBot durduruldu. Sanal pozisyonlar kayitli; yeniden baslatinca izlenir.')
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        logging.error('%s', exc)
        return 1
    except ModuleNotFoundError as exc:
        logging.error('Eksik bagimlilik: %s. requirements.txt paketlerini kurun.', exc.name)
        return 1


if __name__ == '__main__':
    sys.exit(main())
