import discord
import datetime
import config
from database.crud import create_user_ticket

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

class StockTicketControlView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🙋‍♂️ Claim Ticket", style=discord.ButtonStyle.primary, custom_id="stock_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_roles = [r.id for r in interaction.user.roles]
        allowed_roles = [config.Config.SERVER_OVERLORD_ROLE_ID, config.Config.SERVER_WARDEN_ROLE_ID] + config.Config.ADMIN_ROLE_IDS
        
        if not any(role_id in user_roles for role_id in allowed_roles) and not interaction.user.guild_permissions.manage_messages:
             await interaction.response.send_message("❌ Hanya admin yang bisa claim.", ephemeral=True)
             return
        
        button.disabled = True
        button.label = f"Handled by {interaction.user.name}"
        button.style = discord.ButtonStyle.secondary
        
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"Ticket ini sekarang ditangani oleh {interaction.user.mention}")

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="stock_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.ticket_handler.handle_admin_close_ticket(interaction)

class TicketView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

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
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Add Admin Roles (Agar admin bisa lihat ticket)
        for role_id in [config.Config.SERVER_OVERLORD_ROLE_ID, config.Config.SERVER_WARDEN_ROLE_ID] + config.Config.ADMIN_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

        try:
            target_category = None
            if config.Config.STOCK_CATEGORY_ID:
                target_category = guild.get_channel(config.Config.STOCK_CATEGORY_ID)
                if not target_category:
                    print(f"⚠️ Warning: Kategori Stock (ID: {config.Config.STOCK_CATEGORY_ID}) tidak ditemukan. Membuat channel di luar kategori.")

            channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=target_category)
            
            # REGISTER TICKET TO DATABASE (Agar bisa rating saat close)
            await create_user_ticket(
                session=self.bot.session,
                discord_user_id=str(user.id),
                discord_username=user.name,
                ticket_channel_id=str(channel.id)
            )

            embed_ticket = discord.Embed(
                title=f"Ticket Pembelian: {category}",
                description=f"Halo {user.mention}!\nAdmin akan segera memproses pembelian **{category}** kamu.\nSilakan tulis jumlah yang ingin dibeli.",
                color=0x010101
            )
            
            # Pings (User + Admins)
            mentions = [user.mention]
            for role_id in [config.Config.SERVER_OVERLORD_ROLE_ID, config.Config.SERVER_WARDEN_ROLE_ID]:
                role = guild.get_role(role_id)
                if role: mentions.append(role.mention)
            
            view = StockTicketControlView(self.bot)
            await channel.send(content=" ".join(mentions), embed=embed_ticket, view=view)
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

class StockPostApprovalView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="🔒 Close Ticket & End Session", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.ticket_handler.handle_admin_close_ticket(interaction)

class StockPaymentAdminView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="✅ Approve & Send Link", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Cek permission (hanya admin/yang punya izin manage messages)
        if not interaction.user.guild_permissions.manage_messages:
             await interaction.response.send_message("❌ Hanya admin yang bisa melakukan approval.", ephemeral=True)
             return

        # Kirim Link Private Server
        link = config.Config.PRIVATE_SERVER_LINK
        embed = discord.Embed(
            title="✅ Pembayaran Diterima",
            description=f"Terima kasih! Pembayaran kamu telah diverifikasi.\n\n**Silahkan join private server:**\n{link}\n\nHappy Shopping!",
            color=0x00FF00
        )
        
        # Kirim pesan sukses + Tombol Close Ticket
        await interaction.channel.send(content=f"{interaction.message.mentions[0].mention if interaction.message.mentions else ''}", embed=embed, view=StockPostApprovalView(self.bot))
        
        # Matikan tombol
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_messages:
             await interaction.response.send_message("❌ Hanya admin yang bisa reject.", ephemeral=True)
             return

        await interaction.channel.send("❌ **Pembayaran Ditolak.** Silakan cek kembali nominal atau bukti transfer.")
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

async def handle_stock_payment(bot, message):
    description = f"User {message.author.mention} mengirim bukti pembayaran.\nAdmin, silakan cek dan konfirmasi."
    
    # OCR Processing (Auto Read Nominal)
    if message.attachments and bot.config.ENABLE_OCR and hasattr(bot, 'payment_processor') and bot.payment_processor.ocr:
        try:
            # Feedback visual bahwa bot sedang membaca
            temp_msg = await message.channel.send(f"{config.Emojis.LOADING_CIRCLE} **Menganalisis gambar...**")
            
            proof_url = message.attachments[0].url
            detected_amount = await bot.payment_processor.ocr.extract_amount_from_image(proof_url)
            
            if detected_amount > 0:
                description += f"\n\n🤖 **OCR Detected:** Rp {detected_amount:,}"
            
            await temp_msg.delete()
        except Exception as e:
            print(f"⚠️ OCR Error: {e}")
            # Lanjut kirim embed meski OCR gagal

    embed = discord.Embed(title="📸 Bukti Pembayaran Stock", description=description, color=0xFFFF00, timestamp=datetime.datetime.now())
    if message.attachments: embed.set_image(url=message.attachments[0].url)
    await message.channel.send(content=message.author.mention, embed=embed, view=StockPaymentAdminView(bot))