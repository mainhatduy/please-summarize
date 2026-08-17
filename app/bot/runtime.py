"""Shared bot and service instances."""

from discord.ext import commands

from app.services.facebook import FacebookService
from app.services.fortune import FortuneService
from app.services.kinhdich import KinhDichService
from app.services.music import MusicService
from app.services.summarize import SummarizeService
from app.services.taixiu import TaiXiuService
from app.services.tarot import TarotService
from app.services.tiktok import TikTokService
from app.services.xinkeo import XinKeoService

bot = commands.Bot(command_prefix=".", self_bot=True, help_command=None)

summarize_service = SummarizeService()
music_service = MusicService()
facebook_service = FacebookService()
fortune_service = FortuneService()
taixiu_service = TaiXiuService()
xinkeo_service = XinKeoService()
tarot_service = TarotService()
kinhdich_service = KinhDichService()
tiktok_service = TikTokService()
