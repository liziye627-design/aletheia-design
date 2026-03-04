# -*- coding: utf-8 -*-
"""
Bilibili exceptions.
"""

from httpx import RequestError


class DataFetchError(RequestError):
    """Something error when fetch data."""