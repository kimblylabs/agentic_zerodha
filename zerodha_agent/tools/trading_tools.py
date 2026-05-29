from zerodha_agent.services.kite_service import KiteService
from kiteconnect.exceptions import KiteException

kite_service = KiteService()


def get_profile():
    try:
        return kite_service.get_profile()
    except KiteException as e:
        return {"error": str(e)}


def get_holdings():
    try:
        return kite_service.get_holdings()
    except KiteException as e:
        return {"error": str(e)}


def get_positions():
    try:
        return kite_service.get_positions()
    except KiteException as e:
        return {"error": str(e)}


def get_orders():
    try:
        return kite_service.get_orders()
    except KiteException as e:
        return {"error": str(e)}


def get_margins():
    try:
        return kite_service.get_margins()
    except KiteException as e:
        return {"error": str(e)}


def get_quotes(instruments):
    try:
        return kite_service.get_quotes(instruments)
    except KiteException as e:
        return {"error": str(e)}


def get_historical_data(instrument_token, from_date, to_date, interval="day"):
    try:
        return kite_service.get_historical_data(
            instrument_token, from_date, to_date, interval
        )
    except KiteException as e:
        return {"error": str(e)}


def place_order(**kwargs):
    try:
        return kite_service.place_order(**kwargs)
    except KiteException as e:
        return {"error": str(e)}


def modify_order(order_id, **kwargs):
    try:
        return kite_service.modify_order(order_id, **kwargs)
    except KiteException as e:
        return {"error": str(e)}


def cancel_order(order_id):
    try:
        return kite_service.cancel_order(order_id)
    except KiteException as e:
        return {"error": str(e)}
