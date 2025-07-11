import discord
import aiohttp
import asyncio
import json

BOT_TOKEN = ""
TARGET_GUILD_ID = ""

intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)

async def change_nickname(member: discord.Member, new_name: str) -> bool:
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            original_name = member.display_name
            await member.edit(nick=new_name)
            print(f"Successfully changed {original_name} to {new_name}")
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                print(f"Hit Discord rate limit. Waiting {e.retry_after:.2f} seconds...")
                await asyncio.sleep(e.retry_after)
                retry_count += 1
                continue
            else:
                print(f"Failed to change nickname for {member.display_name} ({member.name}): {e}")
                return False
        except discord.Forbidden:
            print(f"Missing permissions to change nickname for {member.display_name} ({member.name})")
            return False
        except Exception as e:
            print(f"Unexpected error changing nickname for {member.display_name} ({member.name}): {e}")
            return False

    print(f"Failed to change nickname for {member.display_name} ({member.name}) after {max_retries} attempts")
    return False

async def fetch_planetearth_data(session: aiohttp.ClientSession, member_id: int):
    api_url = f"https://api.planetearth.kr/discord?discord={member_id}"
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            async with session.get(
                api_url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 429:
                    print("PlanetEarth API rate limited. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    retry_count += 1
                    continue
                elif response.status != 200:
                    print(f"PlanetEarth API returned status {response.status}")
                    return None

                return await response.json()
        except asyncio.TimeoutError:
            print(f"PlanetEarth API timeout (attempt {retry_count + 1})")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(5)
        except Exception as e:
            print(f"Error connecting to PlanetEarth API: {e}")
            return None

    return None

async def fetch_earthpol_data(session: aiohttp.ClientSession, member_id: int):
    api_url = "https://api.earthpol.com/astra/discord"
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            payload = {"query": [str(member_id)]}
            headers = {"Content-Type": "application/json"}

            async with session.post(
                api_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 429:
                    print("EarthPol API rate limited. Waiting 60 seconds...")
                    await asyncio.sleep(60)
                    retry_count += 1
                    continue
                elif response.status != 200:
                    print(f"EarthPol API returned status {response.status}")
                    return None

                return await response.json()
        except asyncio.TimeoutError:
            print(f"EarthPol API timeout (attempt {retry_count + 1})")
            retry_count += 1
            if retry_count < max_retries:
                await asyncio.sleep(5)
        except Exception as e:
            print(f"Error connecting to EarthPol API: {e}")
            return None

    return None

async def fetch_minecraft_name(session: aiohttp.ClientSession, uuid: str):
    mojang_url = f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"

    try:
        async with session.get(
            mojang_url, timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("name")
            else:
                print(f"Mojang API returned status {response.status} for UUID {uuid}")
    except asyncio.TimeoutError:
        print(f"Mojang API timeout for UUID {uuid}")
    except Exception as e:
        print(f"Error fetching Minecraft name for UUID {uuid}: {e}")

    return None

async def update_member_nickname(session: aiohttp.ClientSession, member: discord.Member) -> bool:
    if member.bot or member.guild.id != TARGET_GUILD_ID:
        return False

    # Try EarthPol API first
    earthpol_data = await fetch_earthpol_data(session, member.id)
    if earthpol_data and earthpol_data.get("uuid"):
        uuid = earthpol_data["uuid"].replace("-", "")
    else:
        # Fallback to PlanetEarth API
        planetearth_data = await fetch_planetearth_data(session, member.id)
        if (
            planetearth_data
            and planetearth_data.get("status") == "SUCCESS"
            and planetearth_data.get("data")
        ):
            uuid = planetearth_data["data"][0].get("uuid", "").replace("-", "")
        else:
            print(f"{member.display_name} ({member.name}) hasn't linked their Minecraft account")
            return False

    if not uuid:
        return False

    mc_name = await fetch_minecraft_name(session, uuid)
    if not mc_name:
        return False

    if member.nick == mc_name:
        print(f"{member.display_name} ({member.name}) already has the correct nickname.")
        return True
    else:
        return await change_nickname(member, mc_name)

@client.event
async def on_ready():
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="EarthPol but in Japan"),
    )
    print(f"Logged in as {client.user}")

    guild = client.get_guild(TARGET_GUILD_ID)
    if not guild:
        print(f"Could not find server with ID {TARGET_GUILD_ID}")
        return

    print(f"Starting nickname sync for {guild.name} ({len(guild.members)} members)")

    async with aiohttp.ClientSession() as session:
        success_count = 0
        total_count = 0

        for member in guild.members:
            if not member.bot:
                total_count += 1
                if await update_member_nickname(session, member):
                    success_count += 1
                await asyncio.sleep(1.5)

    print(f"Nickname sync completed for {guild.name}: {success_count}/{total_count} members updated")

@client.event
async def on_member_join(member: discord.Member):
    if member.guild.id == TARGET_GUILD_ID:
        print(f"{member.display_name} ({member.name}) joined {member.guild.name}")
        await asyncio.sleep(1)

        async with aiohttp.ClientSession() as session:
            await update_member_nickname(session, member)

@client.event
async def on_error(event, *args, **kwargs):
    print(f"An error occurred in {event}: {args}")

client.run(BOT_TOKEN)
