import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()


class KiteService:
    def __init__(self):
        self.api_key = os.getenv("ZERODHA_API_KEY")
        self.api_secret = os.getenv("ZERODHA_API_SECRET")
        self.access_token = os.getenv("ZERODHA_ACCESS_TOKEN")
        self.kite = KiteConnect(api_key=self.api_key)
        self.kite.set_access_token(self.access_token)

    def get_profile(self):
        return self.kite.profile()

    def get_holdings(self):
        return self.kite.holdings()

    def get_positions(self):
        return self.kite.positions()

    def get_orders(self):
        return self.kite.orders()

    def get_margins(self):
        return self.kite.margins()

    def get_quotes(self, instruments):
        return self.kite.ltp(instruments)

    def get_historical_data(self, instrument_token, from_date, to_date, interval="day"):
        return self.kite.historical_data(instrument_token, from_date, to_date, interval)

    def place_order(self, **kwargs):
        return self.kite.place_order(variety=self.kite.VARIETY_REGULAR, **kwargs)

    def modify_order(self, order_id, **kwargs):
        return self.kite.modify_order(
            order_id=order_id, variety=self.kite.VARIETY_REGULAR, **kwargs
        )

    def cancel_order(self, order_id):
        return self.kite.cancel_order(
            order_id=order_id, variety=self.kite.VARIETY_REGULAR
        )
