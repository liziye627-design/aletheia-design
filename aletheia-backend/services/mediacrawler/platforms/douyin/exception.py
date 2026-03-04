# -*- coding: utf-8 -*-
"""
Douyin exceptions.
"""

from httpx import RequestError


class DataFetchError(RequestError):
    """Something error when fetch data."""


class IPBlockError(RequestError):
    """Fetch so fast that the server blocked our IP."""