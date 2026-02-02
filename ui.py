import discord
import datetime
import config

def fmt_money(n):
    if n >= 1e9: return f"{n/1e9:.2f}B"
    if n >= 1e6: return f"{n/1e6:.2f}M"
    return f"{n:,.0f}"

def create_dashboard_embed(data):
    embed = discord.Embed(
        title="DVN STOCK", 
        color=0x010101, # Warna Hitam Premium
        timestamp=datetime.datetime.now()
    )

    # 1. SC HIGH LIST
    sc_high_desc = "```ansi\n"
    items = []
    for name, info in data['secrets'].items(): items.append((name, info))
    normals = [x for x in items if not x[1]['is_mutation']]
    mutations = [x for x in items if x[1]['is_mutation']]
    normals.sort(key=lambda x: x[0]); mutations.sort(key=lambda x: x[0])
    sorted_list = normals + mutations
    
    if sorted_list:
        for name, info in sorted_list:
            padding = " " * max(1, 25 - len(name))
            sc_high_desc += f"{info['ansi']}{name}[0m{padding}: [1;37m{info['count']}[0m\n"
    else:
        sc_high_desc += "No High-Tier Secrets.\n"
    sc_high_desc += "```"
    
    embed.add_field(name="SC HIGH TIER", value=sc_high_desc, inline=False)

    # 2. SC LOW & RESOURCES
    embed.add_field(name="SC LOW TIER", value=f"```Total: {data['sc_low_total']} Pcs```", inline=True)
    embed.add_field(name="RUBY GEMSTONE", value=f"```{data['ruby']} Pcs```", inline=True)
    embed.add_field(name="SACRED GUARDIAN SQUID", value=f"```{data['squid']} Pcs```", inline=True)

    # 3. VALUES & MINING
    embed.add_field(name="COIN VIA MYTHIC", value=f"```C$ {fmt_money(data['mythic_value'])}```", inline=True)
    
    mining_txt = f"Evolved: {data['evolved_stone']:,}\nEnchant: {data['enchant_stone']:,}"
    embed.add_field(name="STONE", value=f"```yaml\n{mining_txt}```", inline=True)
    
    # 4. PRICE INFO
    price_info = (
        "• Coin via Mythic : 1K / 2M\n"
        "• Secret Low : 1K / Pcs\n"
        "• Enchant Stone : 1K / 25 Pcs\n"
        "• Evolved Stone : 1K / 4 Pcs\n"
        "• Ruby Gemstone : 50K / Pcs\n"
        "• Lochness Monster : 25K / Pcs"
    )
    embed.add_field(name="PRICE INFO", value=f"```\n{price_info}```", inline=False)
    embed.set_footer(text="DVN Tools • discord.gg/dvn")
    return embed

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def create_ticket(self, interaction: discord.Interaction, category: str):
        guild = interaction.guild
        user = interaction.user
        safe_username = "".join(c for c in user.name if c.isalnum() or c in "-_").lower()
        channel_name = f"ticket-{category.lower().replace(' ', '-')}-{safe_username}"
        
        existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
        if existing_channel:
            await interaction.response.send_message(f"⚠️ Kamu sudah memiliki tiket terbuka untuk kategori ini: {existing_channel.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }

        try:
            channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites)
            embed_ticket = discord.Embed(
                title=f"Ticket Pembelian: {category}",
                description=f"Halo {user.mention}!\nAdmin akan segera memproses pembelian **{category}** kamu.\nSilakan tulis jumlah yang ingin dibeli.",
                color=0x010101
            )
            await channel.send(content=f"{user.mention}", embed=embed_ticket)
            await interaction.response.send_message(f"✅ Tiket berhasil dibuat: {channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Gagal membuat tiket: {e}", ephemeral=True)

    @discord.ui.button(label="Buy SC HIGH", style=discord.ButtonStyle.primary, custom_id="btn_sc_high")
    async def buy_sc_high(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "SC HIGH")

    @discord.ui.button(label="Buy SC LOW", style=discord.ButtonStyle.secondary, custom_id="btn_sc_low")
    async def buy_sc_low(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "SC LOW")

    @discord.ui.button(label="Buy RUBY", style=discord.ButtonStyle.danger, custom_id="btn_ruby")
    async def buy_ruby(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "RUBY")

    @discord.ui.button(label="Buy STONE", style=discord.ButtonStyle.success, custom_id="btn_stone")
    async def buy_stone(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "STONE")

    @discord.ui.button(label="Buy COIN", style=discord.ButtonStyle.primary, custom_id="btn_coin")
    async def buy_coin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "COIN")