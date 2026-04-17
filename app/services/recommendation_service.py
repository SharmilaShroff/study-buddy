from __future__ import annotations

from youtubesearchpython import VideosSearch


class RecommendationService:
    def recommend_videos(self, topic: str, limit: int = 5) -> list[dict]:
        if not topic:
            return []
        search = VideosSearch(topic, limit=limit)
        results = search.result().get("result", [])
        return [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "duration": item.get("duration", ""),
                "channel": item.get("channel", {}).get("name", ""),
            }
            for item in results
        ]
