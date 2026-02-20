import discord
import os
import datetime
import config
from database.crud import create_user_ticket, get_ticket_by_channel, create_user_slot, create_payment_record, update_payment_status
from database.models import UserSlot, PaymentRecord, Patungan
import asyncio
from sqlalchemy import select
from api import process_data
import re
import requests

def fmt_money(n):
    if n >= 1e9: return f"{n/1e9:.2f}B"
    if n >= 1e6: return f"{n/1e6:.2f}M"
    return f"{n:,.0f}"

async def ensure_stock_product(session, name):
    from sqlalchemy import select
    # Truncate if too long
    if len(name) > 100: name = name[:100]
    
    stmt = select(Patungan).where(Patungan.product_name == name)
    result = await session.execute(stmt)
    if not result.scalar_one_or_none():
        p = Patungan(
            product_name=name,
            display_name=name,
            price=0,
            total_slots=9999,
            status='running',
            use_script='No',
            start_mode='full_slot',
            duration_hours=24
        )
        session.add(p)
        await session.flush()
    return name

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
        "• Secret Low : 1K / 2 Pcs\n"
        "• Enchant Stone : 1K / 50 Pcs\n"
        "• Evolved Stone : 1K / 4 Pcs\n"
        "• Ruby Gemstone : 25K / Pcs\n"
        "• Lochness Monster : 10K / Pcs"
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
        
        # Fetch ticket owner for ping
        ticket_owner_ping = ""
        try:
            ticket = await get_ticket_by_channel(self.bot.session, str(interaction.channel.id))
            if ticket:
                ticket_owner_ping = f"<@{ticket.discord_user_id}> "
        except:
            pass
            
        await interaction.channel.send(f"{ticket_owner_ping}Ticket ini sekarang ditangani oleh {interaction.user.mention}")

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="stock_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.bot.ticket_handler.handle_admin_close_ticket(interaction)

async def create_stock_ticket(bot, interaction: discord.Interaction, category: str, sub_category: str, quantity: str, username: str, is_deferred: bool = False):
    guild = interaction.guild
    user = interaction.user
    safe_username = "".join(c for c in user.name if c.isalnum() or c in "-_").lower()
    
    async def send_response(content, ephemeral=True):
        if is_deferred:
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)

    # Category name for channel
    cat_name = category.lower().replace(" ", "-")
    channel_name = f"ticket-{cat_name}-{safe_username}"
    
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
    if existing_channel:
        await send_response(f"⚠️ Kamu sudah memiliki tiket terbuka untuk kategori ini: {existing_channel.mention}")
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    # Add Admin Roles
    for role_id in [config.Config.SERVER_OVERLORD_ROLE_ID, config.Config.SERVER_WARDEN_ROLE_ID] + config.Config.ADMIN_ROLE_IDS:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

    try:
        target_category = None
        if config.Config.STOCK_CATEGORY_ID:
            target_category = guild.get_channel(config.Config.STOCK_CATEGORY_ID)

        channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites, category=target_category)
        
        # REGISTER TICKET TO DATABASE
        success, ticket = await create_user_ticket(
            session=bot.session,
            discord_user_id=str(user.id),
            discord_username=user.name,
            ticket_channel_id=str(channel.id)
        )
        
        # Create UserSlot for Stock (Agar bisa masuk database pembayaran)
        if success and ticket:
             product_name = f"{category} - {sub_category if sub_category else ''}"
             await ensure_stock_product(bot.session, product_name)
             await create_user_slot(
                session=bot.session,
                user_id=str(user.id),
                username=user.name,
                ticket_channel_id=str(channel.id),
                patungan_version=product_name,
                slot_number=1,
                game_username=username,
                display_name=user.display_name,
                locked_price=0 # Harga 0 karena dinamis/belum dihitung
            )

        # Embed Report
        item_name = sub_category if sub_category else category
        qty_suffix = "M" if category == "COIN" else " Pcs"
        
        embed_ticket = discord.Embed(
            title=f"🧾 ORDER DETAILS: {item_name}",
            color=0x010101,
            timestamp=datetime.datetime.now()
        )
        embed_ticket.add_field(name="👤 Buyer", value=user.mention, inline=True)
        embed_ticket.add_field(name="📦 Item", value=item_name, inline=True)
        embed_ticket.add_field(name="🔢 Quantity", value=f"{quantity}{qty_suffix}", inline=True)
        embed_ticket.add_field(name="🎮 Roblox User", value=username, inline=True)
        embed_ticket.set_footer(text="Silakan lakukan pembayaran dan kirim bukti transfer di sini.")
        
        # Pings
        mentions = [user.mention]
        for role_id in [config.Config.SERVER_OVERLORD_ROLE_ID, config.Config.SERVER_WARDEN_ROLE_ID]:
            role = guild.get_role(role_id)
            if role: mentions.append(role.mention)
        
        view = StockTicketControlView(bot)
        await channel.send(content=" ".join(mentions), embed=embed_ticket, view=view)
        await send_response(f"✅ Tiket berhasil dibuat: {channel.mention}")
    except Exception as e:
        await send_response(f"❌ Gagal membuat tiket: {e}")

class StockOrderModal(discord.ui.Modal):
    def __init__(self, bot, category, sub_category=None):
        title = f"Order {sub_category if sub_category else category}"
        if len(title) > 45: title = title[:45]
        super().__init__(title=title)
        self.bot = bot
        self.category = category
        self.sub_category = sub_category

        label_qty = "Jumlah (M)" if category == "COIN" else "Jumlah (Pcs)"
        placeholder_qty = "100 (Artinya 100M)" if category == "COIN" else "100"
        
        self.quantity = discord.ui.TextInput(label=label_qty, placeholder=placeholder_qty, required=True, max_length=20)
        self.add_item(self.quantity)

        self.username = discord.ui.TextInput(label="Username Roblox", placeholder="@username", required=True, max_length=50)
        self.add_item(self.username)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Validasi Stock
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            # Fetch Data Stock Terbaru
            raw_data = await asyncio.to_thread(self.bot.winter_api.fetch_data)
            if not raw_data:
                await interaction.followup.send("❌ Gagal mengambil data stock. Silakan coba lagi.", ephemeral=True)
                return
            
            data = process_data(raw_data)
            
            # Tentukan Stock Tersedia
            available_stock = 0
            if self.category == "SC LOW":
                available_stock = data.get('sc_low_total', 0)
            elif self.category == "COIN":
                available_stock = data.get('mythic_value', 0)
            elif self.category == "STONE":
                if self.sub_category == "Enchant Stone":
                    available_stock = data.get('enchant_stone', 0)
                elif self.sub_category == "Evolved Enchant Stone":
                    available_stock = data.get('evolved_stone', 0)
            
            # Parse Input User
            qty_str = self.quantity.value.lower().replace(',', '').strip()
            multiplier = 1
            
            if 'k' in qty_str:
                multiplier = 1000
                qty_str = qty_str.replace('k', '')
            elif 'm' in qty_str:
                multiplier = 1000000
                qty_str = qty_str.replace('m', '')
            elif 'b' in qty_str:
                multiplier = 1000000000
                qty_str = qty_str.replace('b', '')
            
            try:
                qty_val = float(qty_str) * multiplier
                # Khusus COIN: Jika tidak ada suffix, default = Million (M)
                if self.category == "COIN" and multiplier == 1:
                    qty_val *= 1000000
                qty_val = int(qty_val)
            except ValueError:
                await interaction.followup.send("❌ Format jumlah tidak valid. Harap masukkan angka.", ephemeral=True)
                return

            # Cek Apakah Stock Cukup
            if qty_val > available_stock:
                stock_fmt = fmt_money(available_stock) if self.category == "COIN" else f"{available_stock:,}"
                req_fmt = fmt_money(qty_val) if self.category == "COIN" else f"{qty_val:,}"
                unit = "Coins" if self.category == "COIN" else "Pcs"
                
                await interaction.followup.send(f"⚠️ **STOCK TIDAK CUKUP**\n📉 Permintaan: `{req_fmt} {unit}`\n📦 Tersedia: `{stock_fmt} {unit}`\n\nSilakan kurangi jumlah order.", ephemeral=True)
                return

        except Exception as e:
            await interaction.followup.send(f"❌ Terjadi kesalahan saat cek stock: {e}", ephemeral=True)
            return

        await create_stock_ticket(self.bot, interaction, self.category, self.sub_category, self.quantity.value, self.username.value, is_deferred=True)

class StoneTypeView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=60)
        self.bot = bot

    @discord.ui.select(placeholder="Pilih Tipe Stone...", options=[
        discord.SelectOption(label="Enchant Stone", value="Enchant Stone"),
        discord.SelectOption(label="Evolved Enchant Stone", value="Evolved Enchant Stone")
    ])
    async def select_stone(self, interaction: discord.Interaction, select: discord.ui.Select):
        modal = StockOrderModal(self.bot, "STONE", select.values[0])
        await interaction.response.send_modal(modal)

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
            success, ticket = await create_user_ticket(
                session=self.bot.session,
                discord_user_id=str(user.id),
                discord_username=user.name,
                ticket_channel_id=str(channel.id)
            )
            
            # Create Slot Placeholder
            if success and ticket:
                 await ensure_stock_product(self.bot.session, category)
                 await create_user_slot(
                    session=self.bot.session,
                    user_id=str(user.id),
                    username=user.name,
                    ticket_channel_id=str(channel.id),
                    patungan_version=category,
                    slot_number=1,
                    game_username="Pending Input",
                    display_name=user.display_name,
                    locked_price=0
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
        modal = StockOrderModal(self.bot, "SC LOW")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Buy RUBY", style=discord.ButtonStyle.danger, custom_id="btn_ruby")
    async def buy_ruby(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "RUBY")

    @discord.ui.button(label="Buy STONE", style=discord.ButtonStyle.success, custom_id="btn_stone")
    async def buy_stone(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Pilih tipe stone:", view=StoneTypeView(self.bot), ephemeral=True)

    @discord.ui.button(label="Buy COIN", style=discord.ButtonStyle.primary, custom_id="btn_coin")
    async def buy_coin(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = StockOrderModal(self.bot, "COIN")
        await interaction.response.send_modal(modal)

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

    @discord.ui.button(label="✅ Approve & Send Link", style=discord.ButtonStyle.success, custom_id="stock_approve_btn")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Cek permission (Admin / Overlord / Warden)
        user_roles = [r.id for r in interaction.user.roles]
        allowed_roles = [config.Config.SERVER_OVERLORD_ROLE_ID, config.Config.SERVER_WARDEN_ROLE_ID] + config.Config.ADMIN_ROLE_IDS
        
        if not any(role_id in user_roles for role_id in allowed_roles):
             await interaction.response.send_message("❌ Hanya Admin, Overlord, atau Warden yang bisa melakukan approval.", ephemeral=True)
             return

        await interaction.response.defer()

        # Update Database Status (Verified)
        try:
            ticket = await get_ticket_by_channel(self.bot.session, str(interaction.channel.id))
            if ticket:
                stmt = select(UserSlot).where(UserSlot.ticket_id == ticket.id)
                result = await self.bot.session.execute(stmt)
                slot = result.scalar_one_or_none()
                
                if slot:
                    slot.slot_status = 'paid'
                    slot.payment_verified = True
                    slot.verified_by = interaction.user.name
                    slot.verified_at = datetime.datetime.now()
                    
                    # Update pending payments associated with this slot
                    stmt_pay = select(PaymentRecord).where(
                        PaymentRecord.slot_id == slot.id,
                        PaymentRecord.payment_status == 'pending'
                    )
                    res_pay = await self.bot.session.execute(stmt_pay)
                    payments = res_pay.scalars().all()
                    for p in payments:
                        p.payment_status = 'verified'
                        p.verified_by = interaction.user.name
                        p.verified_at = datetime.datetime.now()
                    
                    await self.bot.session.commit()
        except Exception as e:
            print(f"Error updating DB on approve: {e}")

        # 1. Identifikasi Buyer & Proof
        buyer = interaction.message.mentions[0] if interaction.message.mentions else None
        proof_url = interaction.message.embeds[0].image.url if interaction.message.embeds and interaction.message.embeds[0].image else None
        
        # --- FETCH ORDER DETAILS ---
        roblox_user = "Unknown"
        item_name = "Unknown"
        quantity = "Unknown"
        
        try:
            async for msg in interaction.channel.history(limit=20, oldest_first=True):
                if msg.author.id == self.bot.user.id and msg.embeds:
                    embed = msg.embeds[0]
                    if embed.title and "ORDER DETAILS" in embed.title:
                        for field in embed.fields:
                            if "Item" in field.name: item_name = field.value
                            if "Quantity" in field.name: quantity = field.value
                            if "Roblox User" in field.name: roblox_user = field.value
                        break
        except Exception as e:
            print(f"Error fetching order details: {e}")

        # 2. Kirim Log ke Transaction History
        history_channel = interaction.guild.get_channel(config.Config.TRANSACTION_HISTORY_CHANNEL_ID)
        if history_channel and buyer:
            # Fallback item name if fetch failed
            if item_name == "Unknown":
                try:
                    parts = interaction.channel.name.split('-')
                    if len(parts) > 2:
                        item_name = " ".join(parts[1:-1]).upper()
                    else:
                        item_name = "STOCK ITEM"
                except:
                    item_name = "STOCK ITEM"

            hist_embed = discord.Embed(title=f"{config.Emojis.VERIFIED} **SUCCESSFUL TRANSACTION**", color=config.Config.COLOR_GOLD)
            hist_embed.add_field(name=f"{config.Emojis.TICKET} **Item:**", value=item_name, inline=True)
            hist_embed.add_field(name=f"{config.Emojis.DISCORD_CROWN} **Buyer:**", value=buyer.mention, inline=True)
            hist_embed.add_field(name=f"{config.Emojis.MONEY_BAG} **Price:**", value="*See Proof*", inline=True)
            hist_embed.add_field(name=f"{config.Emojis.NETHERITE_PICKAXE} **Handler:**", value=interaction.user.mention, inline=True)
            
            if proof_url:
                hist_embed.set_image(url=proof_url)
            hist_embed.set_footer(text="DVN Secure Transaction System")
            
            try:
                await history_channel.send(embed=hist_embed)
            except Exception as e:
                print(f"Failed to send history log: {e}")

        # 3. Kirim Link Private Server & Instruksi
        link = config.Config.PRIVATE_SERVER_LINK
        
        receipt_info = (
            f"👤 **Roblox User:** `{roblox_user}`\n"
            f"📦 **Item:** `{item_name}`\n"
            f"🔢 **Quantity:** `{quantity}`"
        )
        
        embed = discord.Embed(
            title="✅ Pembayaran Diterima",
            description=f"Terima kasih! Pembayaran kamu telah diverifikasi.\n\n"
                        f"🧾 **RECEIPT:**\n{receipt_info}\n\n"
                        f"🔗 **PRIVATE SERVER LINK:**\n{link}",
            color=0x00FF00
        )
        
        # Kirim pesan sukses + Tombol Close Ticket
        await interaction.channel.send(content=f"{buyer.mention if buyer else ''}", embed=embed, view=StockPostApprovalView(self.bot))
        
        # Matikan tombol
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger, custom_id="stock_reject_btn")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Cek permission (Admin / Overlord / Warden)
        user_roles = [r.id for r in interaction.user.roles]
        allowed_roles = [config.Config.SERVER_OVERLORD_ROLE_ID, config.Config.SERVER_WARDEN_ROLE_ID] + config.Config.ADMIN_ROLE_IDS
        
        if not any(role_id in user_roles for role_id in allowed_roles):
             await interaction.response.send_message("❌ Hanya Admin, Overlord, atau Warden yang bisa reject.", ephemeral=True)
             return

        # Update Database Status (Rejected)
        try:
            ticket = await get_ticket_by_channel(self.bot.session, str(interaction.channel.id))
            if ticket:
                stmt = select(UserSlot).where(UserSlot.ticket_id == ticket.id)
                result = await self.bot.session.execute(stmt)
                slot = result.scalar_one_or_none()
                if slot:
                    stmt_pay = select(PaymentRecord).where(
                        PaymentRecord.slot_id == slot.id,
                        PaymentRecord.payment_status == 'pending'
                    )
                    res_pay = await self.bot.session.execute(stmt_pay)
                    payments = res_pay.scalars().all()
                    for p in payments:
                        p.payment_status = 'rejected'
                        p.verified_by = interaction.user.name
                    await self.bot.session.commit()
        except Exception as e:
            print(f"Error updating DB on reject: {e}")

        await interaction.channel.send("❌ **Pembayaran Ditolak.** Silakan cek kembali nominal atau bukti transfer.")
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

async def handle_stock_payment(bot, message):
    description = f"User {message.author.mention} mengirim bukti pembayaran.\nAdmin, silakan cek dan konfirmasi."
    detected_amount = 0
    
    # OCR Processing (Auto Read Nominal)
    if message.attachments and bot.config.ENABLE_OCR and hasattr(bot, 'payment_processor') and bot.payment_processor.ocr:
        try:
            # Feedback visual bahwa bot sedang membaca
            temp_msg = await message.channel.send(f"{config.Emojis.LOADING_CIRCLE} **Menganalisis gambar...**")
            
            proof_url = message.attachments[0].url
            detected_amount = await bot.payment_processor.ocr.extract_amount_from_image(proof_url) # Assign to variable
            
            if detected_amount > 0:
                description += f"\n\n🤖 **OCR Detected:** Rp {detected_amount:,}"
            
            await temp_msg.delete()
        except Exception as e:
            print(f"⚠️ OCR Error: {e}")
            # Lanjut kirim embed meski OCR gagal

    # Create Payment Record in DB (Agar muncul di Dashboard)
    try:
        session = bot.session
        ticket = await get_ticket_by_channel(session, str(message.channel.id))
        
        if ticket:
            stmt = select(UserSlot).where(UserSlot.ticket_id == ticket.id)
            result = await session.execute(stmt)
            slot = result.scalar_one_or_none()
            
            if slot:
                # Update slot status
                slot.slot_status = 'waiting_payment'
                
                # Create Payment Record
                await create_payment_record(
                    session=session,
                    slot_id=slot.id,
                    expected_amount=0, # Unknown for stock
                    paid_amount=detected_amount,
                    amount_difference=0,
                    proof_image_url=message.attachments[0].url,
                    payment_status='pending',
                    notes="Stock Payment",
                    user_id=str(message.author.id)
                )
                await session.commit()
    except Exception as e:
        print(f"❌ Failed to create payment record for stock: {e}")

    embed = discord.Embed(title="📸 Bukti Pembayaran Stock", description=description, color=0xFFFF00, timestamp=datetime.datetime.now())
    if message.attachments: embed.set_image(url=message.attachments[0].url)
    await message.channel.send(content=message.author.mention, embed=embed, view=StockPaymentAdminView(bot))