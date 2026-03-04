# -*- coding: utf-8 -*-
"""
XiaoHongShu exceptions.
"""

from httpx import RequestError


class DataFetchError(RequestError):
    """Something error when fetch data."""


class IPBlockError(RequestError):
    """Fetch so fast that the server blocked our IP."""


class NoteNotFoundError(RequestError):
    """Note does not exist or is abnormal."""