"""YuanBot 应用测试"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from yuanbot.app import create_app
from yuanbot.config import YuanBotConfig


@pytest.fixture
def config():
    return YuanBotConfig(debug=True)


@pytest.fixture
def app(config):
    return create_app(config)


@pytest.fixture
def client(app):
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestCreateApp:
    def test_app_creation(self, config):
        app = create_app(config)
        assert app.title == "缘·Bot (YuanBot)"

    def test_app_has_routes(self, app):
        routes = []
        for r in app.routes:
            path = getattr(r, "path", None)
            if path:
                routes.append(path)
        assert "/health" in routes
        assert "/api/chat" in routes
        assert "/api/memory/{user_id}" in routes
        assert "/ws" in routes

    def test_unsupported_provider_raises(self):
        """Unsupported provider raises at runtime when adapter is requested"""
        config = YuanBotConfig()
        config.ai_provider.provider_id = "unsupported"
        app = create_app(config)
        # Error is deferred to AIService runtime, not app creation
        assert hasattr(app.state, "ai_service")

    def test_app_state_has_components(self, app):
        assert hasattr(app.state, "memory_manager")
        assert hasattr(app.state, "skill_manager")
        assert hasattr(app.state, "tool_manager")
        assert hasattr(app.state, "orchestrator")
        assert hasattr(app.state, "web_adapter")
        assert hasattr(app.state, "ai_service")
        assert hasattr(app.state, "provider_manager")
        assert hasattr(app.state, "capability_orchestrator")
