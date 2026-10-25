"""剧本完成后自动抽资产 + 入队分镜的纯逻辑辅助。"""

from app.services.drama.jobs import _episode_has_protected_fragments
from app.models_drama import DramaEpisode, DramaEpisodeFragment


def test_episode_has_protected_fragments_by_video():
    ep = DramaEpisode(name="t", params={"episodeNumber": 1})
    ep.fragments = [
        DramaEpisodeFragment(sort_order=0, content="a", duration_sec=8, video="/x.mp4", params={}),
    ]
    assert _episode_has_protected_fragments(ep) is True


def test_episode_has_protected_fragments_by_user_edit():
    ep = DramaEpisode(name="t", params={"episodeNumber": 1})
    ep.fragments = [
        DramaEpisodeFragment(
            sort_order=0,
            content="a",
            duration_sec=8,
            video="",
            params={"user_edited": True},
        ),
    ]
    assert _episode_has_protected_fragments(ep) is True


def test_episode_unprotected_when_empty_or_plain():
    ep = DramaEpisode(name="t", params={"episodeNumber": 1})
    ep.fragments = [
        DramaEpisodeFragment(sort_order=0, content="a", duration_sec=8, video="", params={}),
    ]
    assert _episode_has_protected_fragments(ep) is False
    ep.fragments = []
    assert _episode_has_protected_fragments(ep) is False
