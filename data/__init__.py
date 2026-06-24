"""Data layer: the DataFeed interface strategies read through."""
from data.feed import DataFeed, NullDataFeed, Candle

__all__ = ["DataFeed", "NullDataFeed", "Candle"]
