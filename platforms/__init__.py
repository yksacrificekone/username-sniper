from .spotify import SpotifyPlatform
from .roblox import RobloxPlatform
from .discord import DiscordPlatform
from .tiktok import TikTokPlatform
from .youtube import YouTubePlatform

PLATFORMS = {
    "spotify": SpotifyPlatform,
    "roblox":  RobloxPlatform,
    "discord": DiscordPlatform,
    "tiktok":  TikTokPlatform,
    "youtube": YouTubePlatform,
}
