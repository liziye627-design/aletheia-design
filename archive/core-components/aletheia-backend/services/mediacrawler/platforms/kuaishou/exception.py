# -*- coding: utf-8 -*-
"""
Kuaishou exceptions.
"""

from httpx import RequestError


class DataFetchError(RequestError):
    """Something error when fetch data."""