"""
modules/court.py - Server Courtroom Discord UI & Trial State
Decoupled from main.py and web_dashboard.py.
"""
import os
import discord
from modules.state_manager import state_mgr

MAIN_CHANNEL_ID = int(os.getenv("MAIN_CHANNEL_ID", 0))


class CourtVoteView(discord.ui.View):
    """Discord UI buttons for Server Courtroom jury voting."""
    def __init__(self, defendant_id: int, defendant_name: str, charge: str, bot_instance):
        super().__init__(timeout=90)
        self.defendant_id = defendant_id
        self.defendant_name = defendant_name
        self.charge = charge
        self.bot = bot_instance
        self.guilty_votes = set()
        self.innocent_votes = set()

    @discord.ui.button(label="🔨 مذنب ويستحق الجلد (0)", style=discord.ButtonStyle.danger, custom_id="vote_guilty")
    async def vote_guilty(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        self.innocent_votes.discard(uid)
        self.guilty_votes.add(uid)
        button.label = f"🔨 مذنب ويستحق الجلد ({len(self.guilty_votes)})"
        for child in self.children:
            if child.custom_id == "vote_innocent":
                child.label = f"🕊️ بريء ومظلوم ({len(self.innocent_votes)})"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="🕊️ بريء ومظلوم (0)", style=discord.ButtonStyle.secondary, custom_id="vote_innocent")
    async def vote_innocent(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        self.guilty_votes.discard(uid)
        self.innocent_votes.add(uid)
        button.label = f"🕊️ بريء ومظلوم ({len(self.innocent_votes)})"
        for child in self.children:
            if child.custom_id == "vote_guilty":
                child.label = f"🔨 مذنب ويستحق الجلد ({len(self.guilty_votes)})"
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        guilty_count = len(self.guilty_votes)
        innocent_count = len(self.innocent_votes)

        target_channel = self.bot.get_channel(MAIN_CHANNEL_ID)
        if not target_channel and self.bot.guilds:
            target_channel = self.bot.guilds[0].system_channel

        if guilty_count >= innocent_count:
            state_mgr.add_crime(self.defendant_id, self.charge)
            verdict_msg = f"⚖️ **نطق بالحكم الرسمي:** بأغلبية {guilty_count} صوت مقابل {innocent_count}... ثبتت إدانة المتهم <@{self.defendant_id}> بالتهمة المنسوبة إليه!\n🔥 العقوبة: الجلد الساخر الفوري وإدراج الجريمة في ملف سوابقه الجنائية!"
            if target_channel:
                await target_channel.send(verdict_msg)
                for g in self.bot.guilds:
                    m = g.get_member(self.defendant_id)
                    if m and hasattr(self.bot, "generate_roast_for_member"):
                        await self.bot.generate_roast_for_member(m, target_channel, custom_topic=f"حكم إدانة من المحكمة بتهمة {self.charge}", custom_intensity=5)
                        break
        else:
            if target_channel:
                await target_channel.send(f"🕊️ **حكم المحكمة:** تم تبرئة <@{self.defendant_id}> بأغلبية أصوات المحلفين ({innocent_count} صوت)! لكن عيون مستر ذبات لا تغفل عنك...")
