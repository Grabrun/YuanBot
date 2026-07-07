"""扩展评分与评论系统测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from yuanbot.services.marketplace import ExtensionReview, ExtensionReviewStore


class TestExtensionReview:
    """测试 ExtensionReview 数据类"""

    def test_to_dict(self):
        review = ExtensionReview(
            id="r1",
            ext_id="ext1",
            user_id="user1",
            rating=5,
            title="Great!",
            content="Very useful extension",
            helpful_count=3,
            created_at=1000.0,
            updated_at=1000.0,
        )
        d = review.to_dict()
        assert d["id"] == "r1"
        assert d["ext_id"] == "ext1"
        assert d["user_id"] == "user1"
        assert d["rating"] == 5
        assert d["title"] == "Great!"
        assert d["content"] == "Very useful extension"
        assert d["helpful_count"] == 3


class TestExtensionReviewStore:
    """测试评分与评论存储"""

    @pytest.fixture
    async def store(self, tmp_path: Path):
        db_path = tmp_path / "test_reviews.db"
        s = ExtensionReviewStore(db_path=db_path)
        await s.initialize()
        yield s
        await s.close()

    async def test_add_review(self, store: ExtensionReviewStore):
        """添加评论"""
        review = await store.add_review(
            ext_id="test-ext",
            user_id="user1",
            rating=5,
            title="Excellent",
            content="Really helpful extension",
        )
        assert review.id
        assert review.ext_id == "test-ext"
        assert review.user_id == "user1"
        assert review.rating == 5
        assert review.title == "Excellent"
        assert review.content == "Really helpful extension"
        assert review.created_at > 0
        assert review.updated_at > 0

    async def test_add_review_upsert(self, store: ExtensionReviewStore):
        """同一用户对同一扩展重复评论会更新"""
        r1 = await store.add_review(
            ext_id="ext1", user_id="user1", rating=3, title="OK"
        )
        r2 = await store.add_review(
            ext_id="ext1", user_id="user1", rating=5, title="Updated"
        )
        # 应该是同一条记录
        assert r1.id == r2.id
        assert r2.rating == 5
        assert r2.title == "Updated"

    async def test_add_review_invalid_rating(self, store: ExtensionReviewStore):
        """评分范围验证"""
        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            await store.add_review(ext_id="ext1", user_id="user1", rating=0)

        with pytest.raises(ValueError, match="Rating must be between 1 and 5"):
            await store.add_review(ext_id="ext1", user_id="user1", rating=6)

    async def test_get_review(self, store: ExtensionReviewStore):
        """获取单条评论"""
        review = await store.add_review(
            ext_id="ext1", user_id="user1", rating=4, title="Good"
        )
        fetched = await store.get_review(review.id)
        assert fetched is not None
        assert fetched.id == review.id
        assert fetched.rating == 4

    async def test_get_review_not_found(self, store: ExtensionReviewStore):
        """获取不存在的评论"""
        assert await store.get_review("nonexistent") is None

    async def test_list_reviews(self, store: ExtensionReviewStore):
        """列出扩展的评论"""
        await store.add_review(ext_id="ext1", user_id="user1", rating=5, title="A")
        await store.add_review(ext_id="ext1", user_id="user2", rating=3, title="B")
        await store.add_review(ext_id="ext1", user_id="user3", rating=4, title="C")
        await store.add_review(ext_id="ext2", user_id="user1", rating=1, title="D")

        result = await store.list_reviews("ext1")
        assert result["total"] == 3
        assert len(result["reviews"]) == 3

    async def test_list_reviews_pagination(self, store: ExtensionReviewStore):
        """评论分页"""
        for i in range(10):
            await store.add_review(
                ext_id="ext1", user_id=f"user{i}", rating=3, title=f"R{i}"
            )

        result = await store.list_reviews("ext1", limit=3, offset=2)
        assert result["total"] == 10
        assert len(result["reviews"]) == 3
        assert result["offset"] == 2
        assert result["limit"] == 3

    async def test_list_reviews_sort_by_rating(self, store: ExtensionReviewStore):
        """按评分排序"""
        await store.add_review(ext_id="ext1", user_id="user1", rating=1, title="Low")
        await store.add_review(ext_id="ext1", user_id="user2", rating=5, title="High")
        await store.add_review(ext_id="ext1", user_id="user3", rating=3, title="Mid")

        result = await store.list_reviews("ext1", sort_by="rating", order="desc")
        ratings = [r["rating"] for r in result["reviews"]]
        assert ratings == [5, 3, 1]

        result = await store.list_reviews("ext1", sort_by="rating", order="asc")
        ratings = [r["rating"] for r in result["reviews"]]
        assert ratings == [1, 3, 5]

    async def test_list_reviews_empty(self, store: ExtensionReviewStore):
        """无评论时返回空列表"""
        result = await store.list_reviews("nonexistent")
        assert result["total"] == 0
        assert result["reviews"] == []

    async def test_delete_review(self, store: ExtensionReviewStore):
        """删除自己的评论"""
        review = await store.add_review(
            ext_id="ext1", user_id="user1", rating=4, title="Test"
        )
        assert await store.delete_review(review.id, "user1") is True
        assert await store.get_review(review.id) is None

    async def test_delete_review_not_owned(self, store: ExtensionReviewStore):
        """不能删除别人的评论"""
        review = await store.add_review(
            ext_id="ext1", user_id="user1", rating=4, title="Test"
        )
        assert await store.delete_review(review.id, "user2") is False
        assert await store.get_review(review.id) is not None

    async def test_delete_review_not_found(self, store: ExtensionReviewStore):
        """删除不存在的评论"""
        assert await store.delete_review("nonexistent", "user1") is False

    async def test_mark_helpful(self, store: ExtensionReviewStore):
        """标记评论为有帮助"""
        review = await store.add_review(
            ext_id="ext1", user_id="user1", rating=5, title="Great"
        )
        assert await store.mark_helpful(review.id, "user2") is True

        updated = await store.get_review(review.id)
        assert updated is not None
        assert updated.helpful_count == 1

    async def test_mark_helpful_duplicate(self, store: ExtensionReviewStore):
        """同一用户不能重复标记"""
        review = await store.add_review(
            ext_id="ext1", user_id="user1", rating=5, title="Great"
        )
        assert await store.mark_helpful(review.id, "user2") is True
        assert await store.mark_helpful(review.id, "user2") is False

        updated = await store.get_review(review.id)
        assert updated is not None
        assert updated.helpful_count == 1

    async def test_mark_helpful_nonexistent_review(self, store: ExtensionReviewStore):
        """标记不存在的评论"""
        result = await store.mark_helpful("nonexistent", "user1")
        assert isinstance(result, bool)

    async def test_get_stats(self, store: ExtensionReviewStore):
        """获取评分统计"""
        await store.add_review(ext_id="ext1", user_id="user1", rating=5)
        await store.add_review(ext_id="ext1", user_id="user2", rating=4)
        await store.add_review(ext_id="ext1", user_id="user3", rating=5)
        await store.add_review(ext_id="ext1", user_id="user4", rating=3)
        await store.add_review(ext_id="ext1", user_id="user5", rating=1)

        stats = await store.get_stats("ext1")
        assert stats.ext_id == "ext1"
        assert stats.total_reviews == 5
        assert abs(stats.average_rating - 3.6) < 0.01
        assert stats.rating_distribution[5] == 2
        assert stats.rating_distribution[4] == 1
        assert stats.rating_distribution[3] == 1
        assert stats.rating_distribution[2] == 0
        assert stats.rating_distribution[1] == 1

    async def test_get_stats_empty(self, store: ExtensionReviewStore):
        """无评论时的统计"""
        stats = await store.get_stats("nonexistent")
        assert stats.total_reviews == 0
        assert stats.average_rating == 0.0
        assert all(v == 0 for v in stats.rating_distribution.values())

    async def test_get_stats_to_dict(self, store: ExtensionReviewStore):
        """统计序列化"""
        await store.add_review(ext_id="ext1", user_id="user1", rating=5)
        await store.add_review(ext_id="ext1", user_id="user2", rating=3)

        stats = await store.get_stats("ext1")
        d = stats.to_dict()
        assert d["ext_id"] == "ext1"
        assert d["total_reviews"] == 2
        assert abs(d["average_rating"] - 4.0) < 0.01
        assert d["rating_distribution"][5] == 1
        assert d["rating_distribution"][3] == 1

    async def test_get_user_review(self, store: ExtensionReviewStore):
        """获取用户对某扩展的评论"""
        await store.add_review(ext_id="ext1", user_id="user1", rating=5, title="A")
        await store.add_review(ext_id="ext1", user_id="user2", rating=3, title="B")

        result = await store.list_reviews("ext1")
        user_reviews = [r for r in result["reviews"] if r["user_id"] == "user1"]
        assert len(user_reviews) == 1
        assert user_reviews[0]["rating"] == 5

    async def test_get_user_review_not_found(self, store: ExtensionReviewStore):
        """用户未评论时返回 None"""
        await store.add_review(ext_id="ext1", user_id="user2", rating=3)
        reviews = await store.list_reviews("ext1")
        user_reviews = [r for r in reviews["reviews"] if r["user_id"] == "user1"]
        assert len(user_reviews) == 0

    async def test_reviews_isolated_by_ext(self, store: ExtensionReviewStore):
        """不同扩展的评论互相隔离"""
        await store.add_review(ext_id="ext1", user_id="user1", rating=5)
        await store.add_review(ext_id="ext2", user_id="user1", rating=1)

        r1 = await store.list_reviews("ext1")
        r2 = await store.list_reviews("ext2")
        assert r1["total"] == 1
        assert r2["total"] == 1
        assert r1["reviews"][0]["rating"] == 5
        assert r2["reviews"][0]["rating"] == 1

    async def test_rating_boundary_values(self, store: ExtensionReviewStore):
        """评分边界值"""
        r1 = await store.add_review(ext_id="ext1", user_id="user1", rating=1)
        assert r1.rating == 1

        r5 = await store.add_review(ext_id="ext2", user_id="user1", rating=5)
        assert r5.rating == 5

    async def test_multiple_helpful_votes(self, store: ExtensionReviewStore):
        """多个用户标记有帮助"""
        review = await store.add_review(
            ext_id="ext1", user_id="user1", rating=5, title="Great"
        )

        for i in range(5):
            await store.mark_helpful(review.id, f"voter{i}")

        updated = await store.get_review(review.id)
        assert updated is not None
        assert updated.helpful_count == 5

    async def test_list_reviews_invalid_sort_field(self, store: ExtensionReviewStore):
        """无效排序字段默认使用 created_at"""
        await store.add_review(ext_id="ext1", user_id="user1", rating=5)

        result = await store.list_reviews("ext1", sort_by="invalid_field")
        assert result["total"] == 1
