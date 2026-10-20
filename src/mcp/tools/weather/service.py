"""weather data should be called in the actual project (current mock; real API to be connected)."""

from __future__ import annotations

import json
from typing import Any

from src.i18n import t
from src.logging import get_logger

logger = get_logger()


def get_weather_payload(args: dict[str, Any]) -> str:
    city = args.get("city", t("北京"))
    logger.info(t('[WeatherTool] 获取 {value1} 的当前天气', value1=city))
    # TODO: The weather API
    weather_data = {
        "city": city,
        "temperature": 25,
        "condition": t("晴朗"),
        "humidity": 45,
        "wind": t("东北风 3级"),
        "aqi": 52,
    }
    return json.dumps(weather_data, ensure_ascii=False)


def get_forecast_payload(args: dict[str, Any]) -> str:
    city = args.get("city", t("北京"))
    days = args.get("days", 3)
    logger.info(t('[WeatherTool] 获取 {value1} 的 {value3} 天天气预报', value1=city, value3=days))
    forecast = [
        {"date": t("今天"), "high": 28, "low": 18, "condition": t("晴")},
        {"date": t("明天"), "high": 26, "low": 17, "condition": t("多云")},
        {"date": t("后天"), "high": 24, "low": 15, "condition": t("小雨")},
    ]
    return json.dumps({"city": city, "forecast": forecast[:days]}, ensure_ascii=False)
