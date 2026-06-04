"""YuanBot 内置工具执行器

提供 Search（联网搜索）和 Weather（天气查询）的真实实现。
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# ---------- Search ----------

_SEARCH_BACKENDS = {
    "bing": "https://api.bing.microsoft.com/v7.0/search",
    "serpapi": "https://serpapi.com/search",
}

async def search_executor(params: dict[str, Any]) -> dict[str, Any]:
    """联网搜索工具执行器

    支持后端：bing / serpapi / duckduckgo (默认免费)
    """
    query = params.get("query", "")
    max_results = params.get("max_results", 5)

    if not query:
        return {"success": False, "error": "query is required"}

    backend = os.getenv("YUANBOT_SEARCH_BACKEND", "duckduckgo")

    try:
        if backend == "bing":
            return await _search_bing(query, max_results)
        elif backend == "serpapi":
            return await _search_serpapi(query, max_results)
        else:
            return await _search_duckduckgo(query, max_results)
    except Exception as exc:
        logger.error("search_failed", backend=backend, error=str(exc))
        return {"success": False, "error": str(exc)}


async def _search_bing(query: str, max_results: int) -> dict[str, Any]:
    """Bing Search API"""
    api_key = os.getenv("YUANBOT_BING_API_KEY", "")
    if not api_key:
        return {"success": False, "error": "YUANBOT_BING_API_KEY not set"}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _SEARCH_BACKENDS["bing"],
            params={"q": query, "count": max_results, "mkt": "zh-CN"},
            headers={"Ocp-Apim-Subscription-Key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()

    results = [
        {
            "title": item.get("name", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
        }
        for item in data.get("webPages", {}).get("value", [])[:max_results]
    ]

    return {"success": True, "query": query, "results": results}


async def _search_serpapi(query: str, max_results: int) -> dict[str, Any]:
    """SerpAPI (Google Search)"""
    api_key = os.getenv("YUANBOT_SERPAPI_KEY", "")
    if not api_key:
        return {"success": False, "error": "YUANBOT_SERPAPI_KEY not set"}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            _SEARCH_BACKENDS["serpapi"],
            params={"q": query, "num": max_results, "api_key": api_key, "engine": "google"},
        )
        resp.raise_for_status()
        data = resp.json()

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        }
        for item in data.get("organic_results", [])[:max_results]
    ]

    return {"success": True, "query": query, "results": results}


async def _search_duckduckgo(query: str, max_results: int) -> dict[str, Any]:
    """DuckDuckGo Instant Answer API (免费，无需 API Key)"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1"},
            headers={"User-Agent": "YuanBot/1.1"},
        )
        resp.raise_for_status()
        data = resp.json()

    results = []

    # Abstract
    abstract = data.get("AbstractText", "")
    abstract_url = data.get("AbstractURL", "")
    if abstract:
        results.append({
            "title": data.get("Heading", query),
            "url": abstract_url,
            "snippet": abstract,
        })

    # Related topics
    results.extend(
        {
            "title": topic.get("Text", "")[:80],
            "url": topic.get("FirstURL", ""),
            "snippet": topic.get("Text", ""),
        }
        for topic in data.get("RelatedTopics", [])[:max_results]
        if isinstance(topic, dict) and "Text" in topic
    )

    if not results:
        results.append({
            "title": query,
            "url": f"https://duckduckgo.com/?q={query}",
            "snippet": f"未找到关于「{query}」的直接结果，建议在浏览器中查看搜索结果。",
        })

    return {"success": True, "query": query, "results": results[:max_results]}


# ---------- Weather ----------

async def weather_executor(params: dict[str, Any]) -> dict[str, Any]:
    """天气查询工具执行器

    支持后端：qweather (和风天气) / openweathermap
    """
    city = params.get("city", "")
    if not city:
        return {"success": False, "error": "city is required"}

    backend = os.getenv("YUANBOT_WEATHER_BACKEND", "qweather")

    try:
        if backend == "openweathermap":
            return await _weather_openweathermap(city)
        else:
            return await _weather_qweather(city)
    except Exception as exc:
        logger.error("weather_failed", city=city, error=str(exc))
        return {"success": False, "error": str(exc)}


async def _weather_qweather(city: str) -> dict[str, Any]:
    """和风天气 API"""
    api_key = os.getenv("YUANBOT_QWEATHER_KEY", "")
    if not api_key:
        # Fallback: 使用 wttr.in 免费 API
        return await _weather_wttr(city)

    # 先查城市 ID
    async with httpx.AsyncClient(timeout=10) as client:
        geo_resp = await client.get(
            "https://geoapi.qweather.com/v2/city/lookup",
            params={"location": city, "key": api_key},
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()

    locations = geo_data.get("location", [])
    if not locations:
        return {"success": False, "error": f"未找到城市「{city}」"}

    location_id = locations[0]["id"]
    city_name = locations[0].get("name", city)

    # 查实时天气
    async with httpx.AsyncClient(timeout=10) as client:
        weather_resp = await client.get(
            "https://devapi.qweather.com/v7/weather/now",
            params={"location": location_id, "key": api_key},
        )
        weather_resp.raise_for_status()
        weather_data = weather_resp.json()

    now = weather_data.get("now", {})
    return {
        "success": True,
        "city": city_name,
        "temperature": now.get("temp", "N/A") + "°C",
        "feels_like": now.get("feelsLike", "N/A") + "°C",
        "weather": now.get("text", "N/A"),
        "humidity": now.get("humidity", "N/A") + "%",
        "wind": f"{now.get('windDir', '')} {now.get('windScale', '')}级",
        "description": (
            f"{city_name}当前天气：{now.get('text', '未知')}，"
            f"气温{now.get('temp', '未知')}°C，体感{now.get('feelsLike', '未知')}°C"
        ),
    }


async def _weather_openweathermap(city: str) -> dict[str, Any]:
    """OpenWeatherMap API"""
    api_key = os.getenv("YUANBOT_OWM_KEY", "")
    if not api_key:
        return await _weather_wttr(city)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": "metric", "lang": "zh_cn"},
        )
        resp.raise_for_status()
        data = resp.json()

    main = data.get("main", {})
    weather = data.get("weather", [{}])[0]
    wind = data.get("wind", {})

    return {
        "success": True,
        "city": data.get("name", city),
        "temperature": f"{main.get('temp', 'N/A')}°C",
        "feels_like": f"{main.get('feels_like', 'N/A')}°C",
        "weather": weather.get("description", "N/A"),
        "humidity": f"{main.get('humidity', 'N/A')}%",
        "wind": f"风速 {wind.get('speed', 'N/A')} m/s",
        "description": (
            f"{data.get('name', city)}当前天气：{weather.get('description', '未知')}，"
            f"气温{main.get('temp', '未知')}°C"
        ),
    }


async def _weather_wttr(city: str) -> dict[str, Any]:
    """wttr.in 免费天气 API (无需 API Key，作为 fallback)"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://wttr.in/{city}",
            params={"format": "j1"},
            headers={"User-Agent": "YuanBot/1.1"},
        )
        resp.raise_for_status()
        data = resp.json()

    current = data.get("current_condition", [{}])[0]
    area = data.get("nearest_area", [{}])[0]
    city_name = area.get("areaName", [{}])[0].get("value", city)

    temp = current.get("temp_C", "N/A")
    feels = current.get("FeelsLikeC", "N/A")
    humidity = current.get("humidity", "N/A")
    desc_list = current.get("lang_zh", current.get("weatherDesc", [{}]))
    desc = desc_list[0].get("value", "未知") if desc_list else "未知"
    wind_dir = current.get("winddir16Point", "")
    wind_speed = current.get("windspeedKmph", "")

    return {
        "success": True,
        "city": city_name,
        "temperature": f"{temp}°C",
        "feels_like": f"{feels}°C",
        "weather": desc,
        "humidity": f"{humidity}%",
        "wind": f"{wind_dir} {wind_speed}km/h",
        "description": f"{city_name}当前天气：{desc}，气温{temp}°C，体感{feels}°C",
    }
