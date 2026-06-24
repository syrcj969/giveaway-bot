import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import json
import os
from datetime import datetime, timedelta
import re

# ========================
#   إعدادات البوت
# ========================
TOKEN = "YOUR_BOT_TOKEN_HERE"       # ← توكن البوت
STAFF_ROLE_ID = 123456789012345678  # ← ID رول الأدمن/الستاف
DATA_FILE = "giveaways.json"        # ملف حفظ الغيفواياتs

# ========================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========================
#   حفظ وتحميل البيانات
# ========================
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

giveaways: dict = load_data()  # { message_id: { prize, prize_url, end_time, winners_count, participants, channel_id, host_id } }


# ========================
#   تحويل المدة النصية لثواني
#   مثال: "10m" -> 600 | "2h" -> 7200 | "1d" -> 86400
# ========================
def parse_duration(text: str) -> int | None:
    text = text.strip().lower()
    match = re.fullmatch(r"(\d+)(s|m|h|d)", text)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers[unit]

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} ثانية"
    elif seconds < 3600:
        return f"{seconds // 60} دقيقة"
    elif seconds < 86400:
        return f"{seconds // 3600} ساعة"
    else:
        return f"{seconds // 86400} يوم"


# ========================
#   View: زر المشاركة
# ========================
class GiveawayView(discord.ui.View):
    def __init__(self, message_id: str):
        super().__init__(timeout=None)
        self.message_id = message_id

    @discord.ui.button(
        label="🎉 شارك",
        style=discord.ButtonStyle.green,
        custom_id="join_giveaway",
    )
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        mid = str(interaction.message.id)
        if mid not in giveaways:
            await interaction.response.send_message("❌ هالغيفواي ما موجود.", ephemeral=True)
            return

        gw = giveaways[mid]
        uid = str(interaction.user.id)

        if uid in gw["participants"]:
            # إلغاء المشاركة
            gw["participants"].remove(uid)
            save_data(giveaways)
            await interaction.response.send_message("↩️ تم إلغاء مشاركتك.", ephemeral=True)
        else:
            gw["participants"].append(uid)
            save_data(giveaways)
            await interaction.response.send_message("✅ تم تسجيلك بالغيفواي! بوفقك 🍀", ephemeral=True)

        # تحديث العداد
        await update_giveaway_embed(interaction.message, mid)


# ========================
#   تحديث الإمبد
# ========================
async def update_giveaway_embed(message: discord.Message, mid: str):
    gw = giveaways.get(mid)
    if not gw:
        return

    end_dt = datetime.fromisoformat(gw["end_time"])
    count = len(gw["participants"])

    embed = message.embeds[0] if message.embeds else discord.Embed()
    embed.set_field_at(0, name="👥 المشاركون", value=f"**{count}** شخص", inline=True)

    try:
        await message.edit(embed=embed)
    except Exception:
        pass


# ========================
#   سحب الفائزين وإنهاء الغيفواي
# ========================
async def end_giveaway(mid: str):
    gw = giveaways.get(mid)
    if not gw:
        return

    channel = bot.get_channel(gw["channel_id"])
    if not channel:
        return

    try:
        message = await channel.fetch_message(int(mid))
    except Exception:
        return

    participants = gw["participants"]
    winners_count = gw["winners_count"]
    prize = gw["prize"]
    prize_url = gw.get("prize_url", "")

    if not participants:
        # لا مشاركين
        embed = discord.Embed(
            title="🎉 انتهى الغيفواي!",
            description="**لا يوجد فائز** — ما حدا شارك 😢",
            color=0xFF0000,
        )
        await message.edit(embed=embed, view=None)
        del giveaways[mid]
        save_data(giveaways)
        return

    # اختيار الفائزين
    actual_count = min(winners_count, len(participants))
    winner_ids = random.sample(participants, actual_count)
    winner_mentions = " ".join(f"<@{uid}>" for uid in winner_ids)

    # تحديث الإمبد
    embed = discord.Embed(
        title="🎉 انتهى الغيفواي!",
        description=f"**الجائزة:** {prize}\n\n🏆 **الفائز/ون:** {winner_mentions}",
        color=0xFFD700,
    )
    if prize_url:
        embed.add_field(name="🔗 الجائزة", value=prize_url, inline=False)
    embed.set_footer(text=f"مجموع المشاركين: {len(participants)}")

    await message.edit(embed=embed, view=None)
    await channel.send(f"🎊 مبروك {winner_mentions}! فزوا بـ **{prize}**!")

    # إرسال DM للفائزين
    for uid in winner_ids:
        member = channel.guild.get_member(int(uid))
        if member:
            try:
                dm_embed = discord.Embed(
                    title="🏆 مبروك! فزت بالغيفواي!",
                    description=f"فزت بـ **{prize}** من سيرفر **{channel.guild.name}** 🎉",
                    color=0xFFD700,
                )
                if prize_url:
                    dm_embed.add_field(name="🔗 الجائزة", value=prize_url, inline=False)
                dm_embed.add_field(
                    name="📌 الغيفواي",
                    value=f"[اضغط هون]({message.jump_url})",
                    inline=False,
                )
                dm_embed.set_footer(text=f"من سيرفر: {channel.guild.name}")
                await member.send(embed=dm_embed)
            except discord.Forbidden:
                pass  # العضو أغلق DM

    del giveaways[mid]
    save_data(giveaways)


# ========================
#   أمر /giveaway
# ========================
@bot.tree.command(name="giveaway", description="🎉 أنشئ غيفواي جديد (أدمن فقط)")
@app_commands.describe(
    prize="اسم الجائزة أو وصفها",
    duration="المدة: مثلاً 10m أو 2h أو 1d",
    winners="عدد الفائزين (افتراضي: 1)",
    prize_url="رابط الجائزة (اختياري)",
)
async def giveaway_cmd(
    interaction: discord.Interaction,
    prize: str,
    duration: str,
    winners: int = 1,
    prize_url: str = "",
):
    # تحقق من الصلاحية
    staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
    if staff_role and staff_role not in interaction.user.roles:
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return

    seconds = parse_duration(duration)
    if not seconds:
        await interaction.response.send_message(
            "❌ صيغة المدة غلط! استخدم مثلاً: `10m` أو `2h` أو `1d`", ephemeral=True
        )
        return

    if winners < 1:
        winners = 1

    end_time = datetime.utcnow() + timedelta(seconds=seconds)

    embed = discord.Embed(
        title="🎉 غيفواي!",
        description=f"**الجائزة:** {prize}\n\nاضغط على 🎉 للمشاركة!",
        color=0x5865F2,
    )
    if prize_url:
        embed.add_field(name="🔗 الجائزة", value=prize_url, inline=False)
    embed.add_field(name="👥 المشاركون", value="**0** شخص", inline=True)
    embed.add_field(name="🏆 الفائزون", value=f"**{winners}**", inline=True)
    embed.add_field(name="⏱ المدة", value=format_duration(seconds), inline=True)
    embed.set_footer(text=f"ينتهي: {end_time.strftime('%Y-%m-%d %H:%M')} UTC | بواسطة: {interaction.user.display_name}")

    await interaction.response.send_message("✅ تم إنشاء الغيفواي!", ephemeral=True)
    msg = await interaction.channel.send(embed=embed, view=GiveawayView("placeholder"))

    # حفظ بيانات الغيفواي
    mid = str(msg.id)
    giveaways[mid] = {
        "prize": prize,
        "prize_url": prize_url,
        "end_time": end_time.isoformat(),
        "winners_count": winners,
        "participants": [],
        "channel_id": interaction.channel.id,
        "host_id": interaction.user.id,
    }
    save_data(giveaways)

    # تحديث الـ View بالـ ID الصح
    await msg.edit(view=GiveawayView(mid))

    # جدولة الإنهاء
    await asyncio.sleep(seconds)
    await end_giveaway(mid)


# ========================
#   أمر /reroll (سحب مجدد)
# ========================
@bot.tree.command(name="reroll", description="🔄 سحب فائز جديد من غيفواي منتهي")
@app_commands.describe(message_id="ID رسالة الغيفواي")
async def reroll_cmd(interaction: discord.Interaction, message_id: str):
    staff_role = interaction.guild.get_role(STAFF_ROLE_ID)
    if staff_role and staff_role not in interaction.user.roles:
        await interaction.response.send_message("❌ ما عندك صلاحية.", ephemeral=True)
        return

    # نجيب المشاركين من الإمبد القديم — الريرول بس يختار عشوائي من الإمبد
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
    except Exception:
        await interaction.response.send_message("❌ ما لقيت الرسالة.", ephemeral=True)
        return

    # نستخرج المشاركين من البيانات المحفوظة (إذا لسا موجودة) أو نطلب يجيب يدوياً
    await interaction.response.send_message(
        "⚠️ الريرول يحتاج البيانات الأصلية. استخدم `/giveaway` لغيفواي جديد أو تواصل مع المطور.",
        ephemeral=True,
    )


# ========================
#   استعادة الغيفوايات عند إعادة التشغيل
# ========================
async def restore_giveaways():
    now = datetime.utcnow()
    to_delete = []
    for mid, gw in giveaways.items():
        end_time = datetime.fromisoformat(gw["end_time"])
        remaining = (end_time - now).total_seconds()
        if remaining <= 0:
            # منتهي وهو offline
            asyncio.create_task(end_giveaway(mid))
        else:
            asyncio.create_task(delayed_end(mid, remaining))

async def delayed_end(mid: str, seconds: float):
    await asyncio.sleep(seconds)
    await end_giveaway(mid)


# ========================
#   تشغيل البوت
# ========================
@bot.event
async def on_ready():
    # تسجيل الـ Views الدائمة
    for mid in giveaways:
        bot.add_view(GiveawayView(mid))

    await bot.tree.sync()
    await restore_giveaways()
    print(f"✅ البوت شغال: {bot.user} | {bot.user.id}")


bot.run(TOKEN)
