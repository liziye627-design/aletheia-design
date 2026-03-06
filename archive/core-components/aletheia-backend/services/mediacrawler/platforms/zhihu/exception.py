# -*- coding: utf-8 -*-
"""
Zhihu exceptions.
"""

from httpx import RequestError


class DataFetchError(RequestError):
    """Something error when fetch data."""