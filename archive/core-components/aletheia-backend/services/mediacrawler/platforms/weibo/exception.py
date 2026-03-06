# -*- coding: utf-8 -*-
"""
Weibo exceptions.
"""

from httpx import RequestError


class DataFetchError(RequestError):
    """Something error when fetch data."""