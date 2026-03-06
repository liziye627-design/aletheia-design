# -*- coding: utf-8 -*-
"""
Tieba exceptions.
"""

from httpx import RequestError


class DataFetchError(RequestError):
    """Something error when fetch data."""