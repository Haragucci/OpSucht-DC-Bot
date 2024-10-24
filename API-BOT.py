import asyncio
import os
import random
import base64
import json
import discord
from discord.ext import commands, tasks
from discord import Intents, Interaction, app_commands
from discord.ui import Button, View
import aiohttp
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CLIENT_ID = os.getenv('CLIENT_ID')
GUILD_ID = os.getenv('GUILD_ID')
API_USERNAME = os.getenv('API_USERNAME')
API_PASSWORD = os.getenv('API_PASSWORD')

intents = Intents.all()
intents.message_content = True
intents.members = True

bot = commands.AutoShardedBot(command_prefix='!', intents=intents)

categories_cache = None
items_cache = {}

API_URL = 'https://api.opsucht.net'

auth_header = base64.b64encode(f"{API_USERNAME}:{API_PASSWORD}".encode()).decode()

headers = {
    'Authorization': f'Basic {auth_header}',
    'User-Agent': 'OpSucht Market Bot v1.0.1'
}

with open('item-translations.json', 'r', encoding='utf-8') as f:
    translations = json.load(f)


@bot.event
async def on_ready():
    print(f'{bot.user} ist nun Online!')
    guild = discord.Object(id=int(GUILD_ID))
    bot.tree.copy_global_to(guild=guild)
    try:
        await bot.tree.sync()
        print('Globale Synchronisierung der Slash-Befehle abgeschlossen.')
    except Exception as e:
        print(f'Fehler bei der globalen Synchronisierung der Slash-Befehle: {e}')


def get_item_image_url(item_name):
    base_url = "https://mc.nerothe.com/img/1.21/"
    formatted_item_name = f"minecraft_{item_name.lower()}"
    return f"{base_url}{formatted_item_name}.png"


@bot.tree.command(name='list_commands', description='Listet alle Slash-Befehle auf')
async def list_commands(interaction: Interaction):
    try:
        url = f'https://discord.com/api/v10/applications/{CLIENT_ID}/commands'
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={'Authorization': f'Bot {TOKEN}'}) as response:
                commands_data = await response.json()

                if not commands_data:
                    await interaction.response.send_message("Keine Slash-Befehle gefunden.")
                else:
                    commands_list = [f"/{cmd['name']}: {cmd['description']}" for cmd in commands_data]
                    commands_message = "\n".join(commands_list)
                    await interaction.response.send_message(f"Liste der Slash-Befehle:\n{commands_message}")
    except aiohttp.ClientError as e:
        print(f'Fehler beim Abrufen der Befehle: {e}')
        await interaction.response.send_message('Fehler beim Abrufen der Befehle.')
    except Exception as e:
        print(f'Unerwarteter Fehler: {e}')
        await interaction.response.send_message('Ein unerwarteter Fehler ist aufgetreten.')


async def get_items(category=None):
    async with aiohttp.ClientSession() as session:
        if category:
            url = f'{API_URL}/market/prices'
        else:
            url = f'{API_URL}/market/items'

        async with session.get(url, headers=headers) as response:
            text = await response.text()
            try:
                data = json.loads(text)
                if category:
                    if category in data:
                        items_cache.update(
                            {item: {'category': category, 'orders': orders} for item, orders in data[category].items()}
                        )
                        return {item: {'category': category} for item in data[category]}
                    else:
                        return {}
                else:
                    all_items = {}
                    for cat, cat_items in data.items():
                        for item, orders in cat_items.items():
                            all_items[item] = {'category': cat, 'orders': orders}
                    return all_items
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                return {}


async def get_items2(category=None):
    async with aiohttp.ClientSession() as session:
        if category:
            url = f'{API_URL}/market/prices'
        else:
            url = f'{API_URL}/market/items'

        async with session.get(url, headers=headers) as response:
            text = await response.text()
            try:
                data = json.loads(text)
                if category:
                    if category in data:
                        items = data[category]
                        items_cache.update(
                            {item: {'category': category, 'orders': orders} for item, orders in items.items()}
                        )
                        return {item: {'category': category} for item in items}
                    else:
                        return {}
                else:
                    all_items = {}
                    for cat, cat_items in data.items():
                        if not isinstance(cat_items, dict):
                            continue
                        for item, orders in cat_items.items():
                            all_items[item] = {'category': cat, 'orders': orders}
                    return all_items

            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                return {}


async def get_all_items():
    global items_cache
    if not items_cache:
        all_items = {}
        categories = await get_categories()
        for category in categories:
            items = await get_items2(category)
            if items:
                if isinstance(items, dict):
                    all_items.update(items)
        items_cache = all_items
    return items_cache


async def get_categories():
    global categories_cache
    if categories_cache is None:
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{API_URL}/market/categories', headers=headers) as response:
                text = await response.text()
                if not text:
                    print("Leere Antwort von der API erhalten")
                    categories_cache = []
                else:
                    try:
                        categories_cache = json.loads(text)
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                        categories_cache = []
    return categories_cache


def create_category_embed(category, items):
    pages = []
    page_size = 10
    emoji_buy = '💰'
    emoji_sell = '🏷️'

    for i in range(0, len(items), page_size):
        page_items = items[i:i + page_size]
        embed = discord.Embed(
            title=f"Kategorie: {category} 🛒",
            description="💰=Kaufpreis | 🏷️=Verkaufspreis | N/A=Nicht verfügbar!",
            color=discord.Color.green()
        )

        for item in page_items:
            formatted_item_name = translations.get(item, item)

            item_details = items_cache.get(item, {})
            orders = item_details.get('orders', [])
            buy_order = next((order for order in orders if order['orderSide'] == 'BUY'), None)
            sell_order = next((order for order in orders if order['orderSide'] == 'SELL'), None)

            buy_price = f"{emoji_buy} {format(buy_order['price'], ',')} $" if buy_order else f"{emoji_buy} N/A"
            sell_price = f"{emoji_sell} {format(sell_order['price'], ',')} $" if sell_order else f"{emoji_sell} N/A"

            embed.add_field(
                name=f"{formatted_item_name}",
                value=f"{buy_price} | {sell_price}",
                inline=True
            )

        embed.set_footer(
            text=f"Seite {len(pages) + 1} von {len(items) // page_size + 1}",
            icon_url=bot.user.avatar.url if bot.user.avatar else None
        )
        embed.timestamp = discord.utils.utcnow()
        pages.append(embed)

    return pages


class PaginationView(View):
    def __init__(self, pages):
        super().__init__()
        self.pages = pages
        self.current_page = 0

        self.previous_button = Button(label='⏪', style=discord.ButtonStyle.primary)
        self.next_button = Button(label='⏩', style=discord.ButtonStyle.primary)
        self.finish_button = Button(label='Fertig', style=discord.ButtonStyle.success)

        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page
        self.finish_button.callback = self.finish

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.finish_button)

    async def previous_page(self, interaction: Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def next_page(self, interaction: Interaction):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    async def finish(self, interaction: Interaction):
        await interaction.message.delete()


@bot.tree.command(name='markt', description='Zeigt Details zu einer Kategorie oder einem bestimmten Item')
@app_commands.describe(
    kategorie="Wähle eine Kategorie",
    item="Optional: Wähle ein Item aus der gewählten Kategorie"
)
async def abfrage(interaction: discord.Interaction, kategorie: str, item: str = None):
    try:
        await interaction.response.defer()

        categories = await get_categories()
        if not categories:
            await interaction.followup.send("Keine Kategorien verfügbar. Bitte versuche es später erneut.")
            return

        if kategorie not in categories:
            await interaction.followup.send(f"Kategorie '{kategorie}' nicht gefunden.")
            return

        items = await get_items(kategorie)
        if not items:
            await interaction.followup.send(f"Keine Items in der Kategorie '{kategorie}' gefunden.")
            return

        if item:
            if item not in items:
                await interaction.followup.send(f"Item '{item}' nicht in der Kategorie '{kategorie}' gefunden.")
                return
            item_details = items_cache.get(item, {})
            orders = item_details.get('orders', [])
            embed = create_item_embed(item, orders, kategorie)
            message = await interaction.followup.send(embed=embed)
        else:
            category_items = list(items.keys())
            pages = create_category_embed(kategorie, category_items)
            view = PaginationView(pages)
            message = await interaction.followup.send(embed=pages[0], view=view)

        await asyncio.sleep(90)
        try:
            await message.delete()
        except discord.NotFound:
            print("Nachricht wurde bereits gelöscht.")

    except aiohttp.ClientError as e:
        print(f'Fehler beim Abrufen der Daten: {e}')
        await interaction.followup.send('Fehler beim Abrufen der Daten vom Server.')
    except Exception as e:
        print(f'Unerwarteter Fehler: {e}')
        await interaction.followup.send('Ein unerwarteter Fehler ist aufgetreten.')


@bot.tree.command(name='markt-item', description='Zeigt Details zu einem bestimmten Item')
@app_commands.describe(dein_item="Gib ein Item ein, um Details dazu zu erhalten")
async def abfrage_item(interaction: discord.Interaction, dein_item: str):
    try:
        await interaction.response.defer()

        items = await get_items2()

        if dein_item not in items:
            await interaction.followup.send(f"Item '{dein_item}' nicht gefunden.")
            return

        item_details = items[dein_item]
        orders = item_details.get('orders', [])
        category = item_details.get('category', None)
        embed = create_item_embed(dein_item, orders, category=category)
        message = await interaction.followup.send(embed=embed)

        await asyncio.sleep(90)
        try:
            await message.delete()
        except discord.NotFound:
            print("Nachricht wurde bereits gelöscht.")

    except aiohttp.ClientError as e:
        print(f'Fehler beim Abrufen der Daten: {e}')
        await interaction.followup.send('Fehler beim Abrufen der Daten vom Server.')
    except Exception as e:
        print(f'Unerwarteter Fehler: {e}')
        await interaction.followup.send('Ein unerwarteter Fehler ist aufgetreten.')


def create_item_embed(item_name, orders, category):
    print(f"Creating embed for item: {item_name}, orders: {orders}, category: {category}")
    emoji_buy = '💰'
    emoji_sell = '🏷️'

    formatted_item_name = translations.get(item_name, item_name)

    item_image_url = get_item_image_url(item_name)
    embed = discord.Embed(
        title=f"**Item:** {formatted_item_name}",
        color=discord.Color.gold()
    )

    if item_image_url:
        embed.set_thumbnail(url=item_image_url)

    embed.add_field(
        name=f"**Kategorie:** {category}",
        value='',
        inline=False
    )

    if orders:
        buy_order = next((order for order in orders if order['orderSide'] == 'BUY'), None)
        sell_order = next((order for order in orders if order['orderSide'] == 'SELL'), None)

        if buy_order:
            embed.add_field(
                name=f"{emoji_buy} **Kaufpreis:** {format(buy_order['price'], ',')} $",
                value="",
                inline=True
            )
        else:
            embed.add_field(
                name=f"{emoji_buy} **Kaufpreis:** N/A",
                value="",
                inline=True
            )

        if sell_order:
            embed.add_field(
                name=f"{emoji_sell} **Verkaufspreis:** {format(sell_order['price'], ',')} $",
                value="",
                inline=False
            )
        else:
            embed.add_field(
                name=f"{emoji_sell} **Verkaufspreis:** N/A",
                value="",
                inline=True
            )

        if buy_order:
            embed.add_field(
                name="**Akt. KauAuf.**",
                value=f"{buy_order['activeOrders']}",
                inline=True
            )
        else:
            embed.add_field(
                name="**Akt. KauAuf.**",
                value="Nicht verfügbar",
                inline=True
            )

        if sell_order:
            embed.add_field(
                name="**Akt. VerAuf.**",
                value=f"{sell_order['activeOrders']}",
                inline=True
            )
        else:
            embed.add_field(
                name="**Akt. VerAuf.**",
                value="N/A",
                inline=True
            )

    else:
        embed.add_field(
            name=f"**Preise**",
            value="N/A",
            inline=True
        )

    embed.set_footer(
        text="Marktpreise",
        icon_url=bot.user.avatar.url if bot.user.avatar else None
    )
    embed.timestamp = discord.utils.utcnow()

    return embed


@abfrage.autocomplete('kategorie')
async def kategorie_autocomplete(interaction: discord.Interaction, current: str):
    try:
        categories = await asyncio.wait_for(get_categories(), timeout=5.0)
        choices = [
                      app_commands.Choice(name=category, value=category)
                      for category in categories if current.lower() in category.lower()
                  ][:25]
        await interaction.response.autocomplete(choices or [])
    except asyncio.TimeoutError:
        await interaction.response.autocomplete([])
    except discord.errors.HTTPException as e:
        if e.status == 404 and e.code == 10062:
            pass
        else:
            raise e


def translate_back(translated_item):
    for item, translation in translations.items():
        if translation == translated_item:
            return item
    return translated_item


@abfrage.autocomplete('item')
async def item_autocomplete(interaction: discord.Interaction, current: str):
    kategorie = interaction.namespace.kategorie
    if not kategorie:
        await interaction.response.autocomplete([])
        return

    items = await get_items(kategorie)

    if items is None:
        await interaction.response.autocomplete([])
        return
    translated_items = {translations.get(item, item): item for item in items}

    choices = [
                  app_commands.Choice(name=translated_item, value=original_item)
                  for translated_item, original_item in translated_items.items()
                  if current.lower() in translated_item.lower() or current.lower() in original_item.lower()
              ][:25]

    await interaction.response.autocomplete(choices)


@abfrage_item.autocomplete('dein_item')
async def item_autocomplete2(interaction: discord.Interaction, current: str):
    try:
        items = await get_all_items()

        if not isinstance(items, dict):
            items = {}

        translated_items = {translations.get(item, item): item for item in items}

        choices = [
                      app_commands.Choice(name=translated_item, value=original_item)
                      for translated_item, original_item in translated_items.items()
                      if current.lower() in translated_item.lower() or current.lower() in original_item.lower()
                  ][:25]

        if choices is None:
            choices = []

        await interaction.response.autocomplete(choices)
    except asyncio.TimeoutError:
        await interaction.response.autocomplete([])
    except discord.errors.HTTPException as e:
        if e.status == 404 and e.code == 10062:
            pass
        else:
            print(f'Fehler bei Autocompletion: {e}')
            await interaction.response.autocomplete([])
    except Exception as e:
        print(f'Unerwarteter Fehler bei Autocompletion: {e}')
        await interaction.response.autocomplete([])


@bot.tree.command(name='help', description='Zeigt alle verfügbaren Befehle')
async def help(interaction: Interaction):
    befehle = [cmd for cmd in bot.tree.get_commands()]
    embed = discord.Embed(title='Help', description='Alle verfügbaren Befehle:', color=0x00FF00)
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.set_footer(text=f"Angefordert von {interaction.user.name}", icon_url=interaction.user.avatar.url)

    for cmd in befehle:
        embed.add_field(name=f"`/{cmd.name}`", value=cmd.description, inline=False)

    await interaction.response.send_message(embed=embed, delete_after=60)


@bot.tree.command(name='info', description='Zeigt Informationen über den Bot')
async def info(interaction: Interaction):
    embed = discord.Embed(title=f"{bot.user.name} Informationen", color=0x00FF00)
    embed.set_thumbnail(url=bot.user.avatar.url)
    embed.add_field(name="Version", value="1.1.5", inline=True)
    embed.add_field(name="Entwickler", value="05Haragucci | Tilljan", inline=True)
    embed.add_field(name="Ping", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.set_footer(text=f"Infos ", icon_url=bot.user.avatar.url)
    embed.timestamp = discord.utils.utcnow()

    await interaction.response.send_message(embed=embed, delete_after=15)


@bot.tree.command(name='clear', description='Löscht den Chat im aktuellen Kanal.')
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_chat(interaction: discord.Interaction):
    if not interaction.user.bot:
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.purge(limit=100)
        followup_message = await interaction.followup.send('Chat wurde gelöscht.', ephemeral=True)
        await followup_message.delete(delay=5)
    else:
        await interaction.response.send_message('Du hast nicht die Berechtigung, diesen Befehl auszuführen.',
                                                ephemeral=True)


@bot.tree.command(name='kick', description='Kickt einen Benutzer vom Server')
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: Interaction, member: discord.Member, reason: str = None):
    await member.kick(reason=reason)
    await interaction.response.send_message(f'{member.mention} wurde vom Server gekickt. Grund: {reason}')


@bot.tree.command(name='ban', description='Bannt einen Benutzer vom Server')
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: Interaction, user: discord.Member, grund: str = None):
    await user.ban(reason=grund)
    await interaction.response.send_message(f'{user.mention} wurde vom Server gebannt. Grund: {grund}')


@bot.tree.command(name='unban', description='Entbannt einen Benutzer')
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: Interaction, user_id: str):
    user = await bot.fetch_user(int(user_id))
    await interaction.guild.unban(user)
    await interaction.response.send_message(f'{user.mention} wurde entbannt.')


@bot.tree.command(name='clearrole', description='Löscht alle rollen eines Users')
async def clearrole(ctx, member: discord.Member):
    await member.edit(roles=[])
    await ctx.send(f'Die rollen des nutzers {member.name} wurden gelöscht.')
    await ctx.message.delete()


@bot.tree.command(name='nachricht', description='Lässt den Bot eine Nachricht in einem bestimmten Kanal senden')
@app_commands.describe(
    channel="Der Kanal, in dem die Nachricht gesendet werden soll",
    nachricht="Die Nachricht, die gesendet werden soll"
)
async def nachricht(interaction: discord.Interaction, channel: discord.TextChannel, nachricht: str):
    try:
        if not channel.permissions_for(interaction.user).send_messages:
            await interaction.response.send_message(
                f"Du hast keine Berechtigung, Nachrichten in {channel.mention} zu senden.", ephemeral=True)
            return

        embed = discord.Embed(description=nachricht, color=0x00ff00)
        embed.set_thumbnail(url=bot.user.avatar.url)
        embed.set_footer(text=f"Nachricht ", icon_url=bot.user.avatar.url)
        embed.timestamp = discord.utils.utcnow()

        await channel.send(embed=embed)

        try:
            await interaction.response.send_message(f"Nachricht wurde erfolgreich in {channel.mention} gesendet.",
                                                    ephemeral=True)
        except discord.NotFound:
            pass

    except discord.Forbidden:
        await interaction.response.send_message("Ich habe keine Berechtigung, Nachrichten in diesem Kanal zu senden.",
                                                ephemeral=True)
    except discord.HTTPException:
        await interaction.response.send_message("Es gab einen Fehler beim Senden der Nachricht.", ephemeral=True)


@bot.tree.command(name='umfrage', description='Erstellt eine stylische Umfrage mit zwei Optionen')
async def poll(interaction: Interaction, frage: str, option1: str, option2: str, mehrfachauswahl: bool):
    await interaction.response.send_message('🎉 Die Umfrage wird erstellt... 🗳️', ephemeral=True)

    multiple_choice_text = " ✅ Ja" if mehrfachauswahl else " ❌ Nein"

    embed = discord.Embed(
        title="📊 **Umfrage**",
        description=f"**{frage}**\n\nMerfach Antwort möglich: {multiple_choice_text}",
        color=discord.Color.from_rgb(47, 49, 54)
    )

    embed.add_field(
        name="🔵 **Option 1**",
        value=option1,
        inline=True
    )
    embed.add_field(
        name="\n\n🟢 **Option 2**",
        value=option2,
        inline=True
    )

    embed.set_footer(
        text="⬇️ Wähle durch Anklicken der Reaktionen unten! ⬇️",
        icon_url=bot.user.avatar.url
    )
    embed.timestamp = discord.utils.utcnow() + timedelta(hours=2)

    message = await interaction.channel.send(embed=embed)
    await message.add_reaction('🔵')
    await message.add_reaction('🟢')

    def check(reaction, user):
        return user != bot.user and reaction.message.id == message.id and reaction.emoji in ['🔵', '🟢']

    while True:
        try:
            reaction, user = await bot.wait_for('reaction_add', check=check)
            if not mehrfachauswahl:
                if reaction.emoji == '🔵':
                    await message.remove_reaction('🟢', user)
                elif reaction.emoji == '🟢':
                    await message.remove_reaction('🔵', user)
        except asyncio.TimeoutError:
            break


@bot.tree.command(name='test', description='Führt einen Test aus im Channel')
async def test(ctx):
    await ctx.send('Der bot funktioniert einwandfrei!')


@tasks.loop(minutes=10)
async def change_status():
    statuses = ['auf OPSUCHT', 'mit APIs', 'mit Daten']
    await bot.change_presence(activity=discord.Game(random.choice(statuses)))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Dieser Befehl existiert nicht. Benutze `/help` für eine Liste aller Befehle.")


bot.run(TOKEN)
