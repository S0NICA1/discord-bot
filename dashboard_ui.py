import discord
from discord.ui import View, Button, Select

class UserSelect(Select):
    def __init__(self, bot, generate_roast_callback):
        self.bot = bot
        self.generate_roast_callback = generate_roast_callback
        
        options = []
        for guild in bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        options.append(discord.SelectOption(
                            label=member.display_name,
                            description=f"In {vc.name}",
                            value=str(member.id)
                        ))
        if not options:
            options.append(discord.SelectOption(label="No users in VC", value="none"))
        
        super().__init__(
            placeholder="Select a user to roast...", 
            min_values=1, 
            max_values=1, 
            options=options[:25] # Select menu can have a max of 25 options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No users available to roast.", ephemeral=True)
            return
            
        user_id = int(self.values[0])
        member = interaction.guild.get_member(user_id)
        if member:
            await interaction.response.send_message(f"Generating roast for {member.display_name}...", ephemeral=True)
            await self.generate_roast_callback(member, interaction.channel)
        else:
            await interaction.response.send_message("User not found.", ephemeral=True)


class DashboardView(View):
    def __init__(self, bot, toggle_loop_callback, force_roast_callback, generate_roast_callback):
        super().__init__(timeout=None)
        self.bot = bot
        self.toggle_loop_callback = toggle_loop_callback
        self.force_roast_callback = force_roast_callback
        self.generate_roast_callback = generate_roast_callback
        
        # Add the select menu
        self.add_item(UserSelect(bot, generate_roast_callback))

    @discord.ui.button(label="Pause/Resume Auto-Roast", style=discord.ButtonStyle.primary, custom_id="toggle_roast_loop")
    async def toggle_loop_btn(self, interaction: discord.Interaction, button: Button):
        is_running = await self.toggle_loop_callback()
        status = "Resumed" if is_running else "Paused"
        await interaction.response.send_message(f"Auto-roast loop has been **{status}**.", ephemeral=True)

    @discord.ui.button(label="Force Random Roast", style=discord.ButtonStyle.danger, custom_id="force_random_roast")
    async def force_roast_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Forcing random roast...", ephemeral=True)
        await self.force_roast_callback(interaction.channel)
