# -*- coding: utf-8 -*-
"""
Telegram 私域运营机器人 v2
功能: 语言选择(中/EN) · 签到/连续签到 · 积分 · 邀请统计 · 邀请榜
      统一帮助菜单(/help + 按钮) · 绑定账号 · 提现申请 · 新手教程
框架: aiogram 3.x   存储: SQLite (零月费)
特点: 用户首次进来先选语言, 之后只发对应语言; 零散指令全部并进一个【帮助】菜单。
所有文案集中在下方 TEXTS 字典, 改文案只动那一处。
"""

import asyncio
import os
import logging
import sqlite3
from datetime import date, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

# ====================== 配置区 (只改这里就够了) ======================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROUP_LINK = "https://t.me/earn9292"
CHANNEL_LINK = "https://t.me/channelich_55rich"
SUPPORT_CONTACT = "@rich090807"   # 用户点"联系客服"会看到

DAILY_POINTS = 10        # 每日签到
STREAK_BONUS = 50        # 连续满 N 天额外奖
STREAK_DAYS = 7          # 连续天数门槛
INVITE_REWARD = 100      # 邀请人奖励
INVITEE_REWARD = 30      # 新人奖励
WITHDRAW_MIN = 2000      # 提现最低积分门槛 (调它=调成本, 高门槛降真实支出)

REWARD_TRIGGER = "join"  # "join"=新人一来就发 / "signin"=新人首签才发(防刷)

# 迁移口令: WS用户输入它领启动金 (每人只能领一次)
MIGRATION_CODE = "WS2026"      # 口令(不区分大小写)
MIGRATION_BONUS = 500          # 输对口令领多少积分

# 自动发邀请榜: 每天到这个小时(0-23, 服务器时区)自动把榜单发到群
RANK_PUSH_HOUR = 20            # 20 = 晚8点; 设为 -1 关闭自动发
RANK_PUSH_CHAT = "@earn9292"   # 榜单发到哪 (群用户名或频道用户名)

# 提现申请通知给谁 (你的Telegram数字ID, 用 @userinfobot 查; 不填则不通知)
ADMIN_ID = 8915875126                   # 例如 123456789; 0=不通知

DB_FILE = "bot_data.db"
# =====================================================================

# ====================== 文案区 (双语, 改文案只动这里) ==================
TEXTS = {
    "zh": {
        "choose_lang": "请选择语言 / Please choose your language：",
        "welcome": (
            "👋 欢迎你，{name}！\n\n在这里你可以：\n"
            "✅ 每天签到赚积分（连续 {days} 天额外 +{bonus}）\n"
            "👥 邀请好友，每人 +{invite} 积分\n🏆 冲上邀请榜，赢更多奖励\n\n点下方按钮开始 👇"
        ),
        "btn_signin": "✅ 签到", "btn_points": "💰 我的积分", "btn_invite": "👥 邀请赚钱",
        "btn_rank": "🏆 邀请榜", "btn_help": "❓ 帮助", "btn_withdraw": "💰 兑换提现",
        "already_signed": "今天已经签到过啦，明天再来～\n当前积分：{pts}",
        "signin_ok": "✅ 签到成功！+{earned} 积分{bonus}\n已连续签到 {streak} 天\n当前总积分：{pts}",
        "streak_bonus": "\n🔥 连续签到满 {days} 天，额外 +{n}！",
        "my_points": "💰 你的积分：{pts}\n🔥 连续签到：{streak} 天\n👥 已邀请：{invites} 人\n\n你的专属邀请链接：\n{link}",
        "invite_msg": (
            "👥 邀请好友，每成功邀请 1 人 +{invite} 积分！\n对方也能得 {invitee} 积分，双赢～\n\n"
            "① 复制你的专属链接发给好友：\n{link}\n\n② 让好友点链接打开机器人，奖励自动到账\n"
            "③ 别忘了拉他进群：{group}\n\n你已成功邀请 {invites} 人。"
        ),
        "invite_got": "🎉 恭喜！你邀请的好友已加入，+{invite} 积分已到账！继续邀请赚更多 👇",
        "rank_title": "🏆 邀请榜 TOP 10\n", "rank_empty": "🏆 邀请榜还没人上榜，快去邀请好友抢第一名！",
        "rank_line": "{rank} {name} — 邀请 {n} 人", "rank_foot": "\n继续邀请，冲上榜首赢额外大奖！",
        "help_title": "❓ 帮助中心 — 请选择你需要的：",
        "help_tips": "📖 新手教程", "help_bind": "🔗 绑定平台账号", "help_withdraw": "💰 兑换提现",
        "help_faq": "📋 常见问题", "help_support": "🧑‍💻 联系客服", "help_back": "⬅ 返回",
        "tips_content": (
            "📖 <b>新手 3 步开始赚钱</b>\n\n1️⃣ 每天点【✅ 签到】领积分，连续签到奖励更高\n"
            "2️⃣ 点【👥 邀请赚钱】把专属链接发给好友，每拉 1 人 +{invite} 分\n"
            "3️⃣ 积分攒够 {min} 分，进【❓帮助 → 💰兑换提现】兑换到平台账号提现\n\n频道看活动：{channel}\n群里聊天互助：{group}"
        ),
        "bind_ask": "🔗 <b>绑定平台账号</b>\n\n请直接回复你在平台的账号 / UID，\n我会帮你保存，兑换时积分会转到这个账号。\n\n格式：直接发送你的平台UID即可。",
        "bind_ok": "✅ 平台账号已绑定：{acct}\n如需修改，重新进入此菜单即可。",
        "bind_current": "你当前已绑定平台账号：{acct}\n如需修改，请直接回复新的平台UID。",
        "withdraw_info": "💰 <b>兑换提现</b>\n\n当前积分：{pts}\n兑换门槛：{min} 分\n平台账号：{acct}\n\n你的积分将按 1:1 兑换到平台账号，在平台完成提现。\n\n{status}",
        "withdraw_no_acct": "⚠ 你还没绑定平台账号，请先到【🔗 绑定平台账号】。",
        "withdraw_not_enough": "⚠ 积分不足 {min} 分，继续签到和邀请攒积分吧！",
        "withdraw_ok": "✅ 提现申请已提交！客服会尽快为你处理，请留意 {contact} 的消息。",
        "withdraw_btn": "确认兑换到平台",
        "faq_content": (
            "📋 <b>常见问题</b>\n\n<b>Q：积分有什么用？</b>\nA：可按 1:1 兑换到平台账号提现，也可参与抽奖。\n\n"
            "<b>Q：邀请奖励多久到账？</b>\nA：好友打开机器人立即到账。\n\n"
            "<b>Q：为什么连续签到断了？</b>\nA：漏签一天会重置，记得每天来。\n\n"
            "<b>Q：兑换多久到账？</b>\nA：申请后客服人工转入平台，请耐心等待，之后在平台提现。"
        ),
        "support_content": "🧑‍💻 联系客服：{contact}\n（请说明你的问题，我们会尽快回复）",
        "fallback": "点下方按钮操作哦 👇",
        "code_ok": "🎁 口令正确！+{n} 积分启动金已到账！\n现在去签到、邀请好友赚更多吧 👇",
        "code_used": "你已经领过启动金啦，不能重复领取～",
        "code_wrong": "口令不对哦。如果你是从 WhatsApp 过来的，请核对公告里的口令。",
        "withdraw_done_deduct": "✅ 兑换申请已提交！已扣除 {min} 积分，将按 1:1 转入你的平台账号。客服处理后请到平台查看，有问题联系 {contact}。",
        "withdraw_confirm": "⚠️ <b>请核对你的平台账号</b>\n\n积分将转入这个平台账号：\n<b>{acct}</b>\n\n兑换积分：{min}\n\n确认无误再点下方按钮，转错账号无法找回！\n账号填错了？先去【🔗 绑定平台账号】改正。",
        "withdraw_confirm_btn": "✅ 确认账号无误，兑换",
        "btn_bind_now": "🔗 绑定账号", "btn_bind_edit": "✏️ 修改账号",
    },
    "en": {
        "choose_lang": "请选择语言 / Please choose your language：",
        "welcome": (
            "👋 Welcome, {name}!\n\nHere you can:\n"
            "✅ Check in daily for points ({days}-day streak gives +{bonus})\n"
            "👥 Invite friends, +{invite} points each\n🏆 Top the invite leaderboard for bigger rewards\n\nTap a button below to start 👇"
        ),
        "btn_signin": "✅ Check in", "btn_points": "💰 My Points", "btn_invite": "👥 Invite & Earn",
        "btn_rank": "🏆 Leaderboard", "btn_help": "❓ Help", "btn_withdraw": "💰 Exchange",
        "already_signed": "You've already checked in today, come back tomorrow~\nPoints: {pts}",
        "signin_ok": "✅ Checked in! +{earned} points{bonus}\nStreak: {streak} days\nTotal points: {pts}",
        "streak_bonus": "\n🔥 {days}-day streak bonus +{n}!",
        "my_points": "💰 Points: {pts}\n🔥 Streak: {streak} days\n👥 Invited: {invites} people\n\nYour invite link:\n{link}",
        "invite_msg": (
            "👥 Invite friends — +{invite} points per successful invite!\nYour friend also gets {invitee} points. Win-win~\n\n"
            "① Copy your link and send it to friends:\n{link}\n\n② When they open the bot, rewards are credited automatically\n"
            "③ Don't forget to bring them to the group: {group}\n\nYou've invited {invites} people."
        ),
        "invite_got": "🎉 Your invited friend joined! +{invite} points credited. Keep inviting 👇",
        "rank_title": "🏆 Invite Leaderboard TOP 10\n", "rank_empty": "🏆 No one on the board yet — invite friends and grab #1!",
        "rank_line": "{rank} {name} — {n} invites", "rank_foot": "\nKeep inviting to reach the top and win big!",
        "help_title": "❓ Help Center — pick what you need:",
        "help_tips": "📖 Getting Started", "help_bind": "🔗 Bind Platform Account", "help_withdraw": "💰 Exchange & Withdraw",
        "help_faq": "📋 FAQ", "help_support": "🧑‍💻 Support", "help_back": "⬅ Back",
        "tips_content": (
            "📖 <b>Start earning in 3 steps</b>\n\n1️⃣ Tap [✅ Check in] daily; longer streaks earn more\n"
            "2️⃣ Tap [👥 Invite & Earn] and share your link; +{invite} per invite\n"
            "3️⃣ Once you reach {min} points, go to [❓Help → 💰Exchange] to convert to your platform account\n\nChannel for events: {channel}\nGroup chat: {group}"
        ),
        "bind_ask": "🔗 <b>Bind your platform account</b>\n\nReply with your platform account / UID.\nPoints will be converted to this account.\n\nJust send your platform UID directly.",
        "bind_ok": "✅ Platform account bound: {acct}\nTo change it, open this menu again.",
        "bind_current": "Current platform account: {acct}\nReply with a new UID to change it.",
        "withdraw_info": "💰 <b>Exchange &amp; Withdraw</b>\n\nPoints: {pts}\nMinimum: {min}\nPlatform account: {acct}\n\nYour points convert 1:1 to your platform account, withdraw there.\n\n{status}",
        "withdraw_no_acct": "⚠ No platform account yet. Please go to [🔗 Bind Platform Account] first.",
        "withdraw_not_enough": "⚠ Below {min} points. Keep checking in and inviting!",
        "withdraw_ok": "✅ Withdrawal request submitted! Support will handle it soon. Watch for messages from {contact}.",
        "withdraw_btn": "Confirm exchange to platform",
        "faq_content": (
            "📋 <b>FAQ</b>\n\n<b>Q: What are points for?</b>\nA: Exchange 1:1 to your platform account to withdraw, or join lucky draws.\n\n"
            "<b>Q: When do invite rewards arrive?</b>\nA: Instantly when your friend opens the bot.\n\n"
            "<b>Q: Why did my streak reset?</b>\nA: Missing a day resets it. Come daily!\n\n"
            "<b>Q: How long for exchange?</b>\nA: Manually transferred to the platform by support; withdraw there afterwards."
        ),
        "support_content": "🧑‍💻 Support: {contact}\n(Describe your issue, we'll reply soon)",
        "fallback": "Tap a button below 👇",
        "code_ok": "🎁 Correct code! +{n} starter points credited!\nNow check in and invite friends to earn more 👇",
        "code_used": "You've already claimed the starter bonus~",
        "code_wrong": "Wrong code. If you came from WhatsApp, please check the code in the announcement.",
        "withdraw_done_deduct": "✅ Exchange submitted! {min} points deducted, will be transferred 1:1 to your platform account. Check the platform after processing; contact {contact} if needed.",
        "withdraw_confirm": "⚠️ <b>Please verify your platform account</b>\n\nPoints will go to:\n<b>{acct}</b>\n\nExchange: {min} points\n\nConfirm only if correct — wrong account cannot be recovered!\nWrong account? Go to [🔗 Bind Platform Account] to fix it.",
        "withdraw_confirm_btn": "✅ Account is correct, exchange",
        "btn_bind_now": "🔗 Bind Account", "btn_bind_edit": "✏️ Edit Account",
    },
}
# =====================================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
BOT_USERNAME = ""
awaiting_bind = set()


def T(lang, key, **kw):
    lang = lang if lang in TEXTS else "zh"
    return TEXTS[lang][key].format(**kw)


def db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
            lang TEXT DEFAULT 'zh', points INTEGER DEFAULT 0, invited_by INTEGER,
            last_signin TEXT, streak INTEGER DEFAULT 0, total_invites INTEGER DEFAULT 0,
            rewarded INTEGER DEFAULT 0, account TEXT, code_claimed INTEGER DEFAULT 0,
            created_at TEXT
        )""")
    conn.commit()
    conn.close()


def get_user(uid):
    conn = db()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return row


def create_user(uid, username, first_name, invited_by=None):
    conn = db()
    conn.execute("INSERT OR IGNORE INTO users (user_id,username,first_name,invited_by,created_at) VALUES (?,?,?,?,?)",
                 (uid, username, first_name, invited_by, date.today().isoformat()))
    conn.commit()
    conn.close()


def set_field(uid, field, value):
    conn = db()
    conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, uid))
    conn.commit()
    conn.close()


def lang_of(uid):
    u = get_user(uid)
    return (u["lang"] if u and u["lang"] else "zh")


def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇨🇳 中文", callback_data="lang_zh"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    ]])


def main_menu(lang):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=T(lang, "btn_signin")), KeyboardButton(text=T(lang, "btn_invite"))],
        [KeyboardButton(text=T(lang, "btn_points")), KeyboardButton(text=T(lang, "btn_rank"))],
        [KeyboardButton(text=T(lang, "btn_withdraw")), KeyboardButton(text=T(lang, "btn_help"))],
    ], resize_keyboard=True)


def help_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T(lang, "help_tips"), callback_data="h_tips"),
         InlineKeyboardButton(text=T(lang, "help_faq"), callback_data="h_faq")],
        [InlineKeyboardButton(text=T(lang, "help_support"), callback_data="h_support")],
    ])


def back_menu(lang):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=T(lang, "help_back"), callback_data="h_home")]])


def reward_inviter(invitee_row):
    inviter_id = invitee_row["invited_by"]
    if not inviter_id or invitee_row["rewarded"] == 1:
        return None
    if not get_user(inviter_id):
        return None
    conn = db()
    conn.execute("UPDATE users SET points=points+?, total_invites=total_invites+1 WHERE user_id=?",
                 (INVITE_REWARD, inviter_id))
    conn.execute("UPDATE users SET points=points+?, rewarded=1 WHERE user_id=?",
                 (INVITEE_REWARD, invitee_row["user_id"]))
    conn.commit()
    conn.close()
    return inviter_id


@dp.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    uid = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    ref = None
    if command.args and command.args.isdigit():
        ref = int(command.args)
        if ref == uid:
            ref = None
    existing = get_user(uid)
    if existing is None:
        create_user(uid, username, first_name, invited_by=ref)
        await message.answer(TEXTS["zh"]["choose_lang"], reply_markup=lang_keyboard())
    else:
        lang = existing["lang"] or "zh"
        await message.answer(
            T(lang, "welcome", name=first_name, days=STREAK_DAYS, bonus=STREAK_BONUS, invite=INVITE_REWARD),
            reply_markup=main_menu(lang))


@dp.callback_query(F.data.startswith("lang_"))
async def on_lang(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = cb.data.split("_")[1]
    set_field(uid, "lang", lang)
    user = get_user(uid)
    if user and user["invited_by"] and REWARD_TRIGGER == "join" and user["rewarded"] == 0:
        inviter_id = reward_inviter(user)
        if inviter_id:
            try:
                await bot.send_message(inviter_id, T(lang_of(inviter_id), "invite_got", invite=INVITE_REWARD))
            except Exception:
                pass
    await cb.message.edit_text(
        T(lang, "welcome", name=cb.from_user.first_name or "", days=STREAK_DAYS, bonus=STREAK_BONUS, invite=INVITE_REWARD))
    await bot.send_message(uid, "👇", reply_markup=main_menu(lang))
    await cb.answer()


@dp.message(F.text.in_({TEXTS["zh"]["btn_signin"], TEXTS["en"]["btn_signin"]}))
async def sign_in(message: Message):
    uid = message.from_user.id
    user = get_user(uid)
    if not user:
        create_user(uid, message.from_user.username or "", message.from_user.first_name or "")
        user = get_user(uid)
    lang = user["lang"] or "zh"
    today = date.today()
    if user["last_signin"] == today.isoformat():
        await message.answer(T(lang, "already_signed", pts=user["points"]))
        return
    streak = user["streak"] or 0
    streak = streak + 1 if user["last_signin"] == (today - timedelta(days=1)).isoformat() else 1
    earned = DAILY_POINTS
    bonus = ""
    if streak % STREAK_DAYS == 0:
        earned += STREAK_BONUS
        bonus = T(lang, "streak_bonus", days=STREAK_DAYS, n=STREAK_BONUS)
    conn = db()
    conn.execute("UPDATE users SET points=points+?, last_signin=?, streak=? WHERE user_id=?",
                 (earned, today.isoformat(), streak, uid))
    conn.commit()
    conn.close()
    user = get_user(uid)
    await message.answer(T(lang, "signin_ok", earned=earned, bonus=bonus, streak=streak, pts=user["points"]))


@dp.message(F.text.in_({TEXTS["zh"]["btn_points"], TEXTS["en"]["btn_points"]}))
async def my_points(message: Message):
    uid = message.from_user.id
    user = get_user(uid)
    if not user:
        return
    lang = user["lang"] or "zh"
    link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    await message.answer(T(lang, "my_points", pts=user["points"], streak=user["streak"] or 0,
                           invites=user["total_invites"] or 0, link=link))


@dp.message(F.text.in_({TEXTS["zh"]["btn_invite"], TEXTS["en"]["btn_invite"]}))
async def invite(message: Message):
    uid = message.from_user.id
    user = get_user(uid)
    if not user:
        return
    lang = user["lang"] or "zh"
    link = f"https://t.me/{BOT_USERNAME}?start={uid}"
    await message.answer(T(lang, "invite_msg", invite=INVITE_REWARD, invitee=INVITEE_REWARD,
                           link=link, group=GROUP_LINK, invites=user["total_invites"] or 0))


@dp.message(F.text.in_({TEXTS["zh"]["btn_rank"], TEXTS["en"]["btn_rank"]}))
async def leaderboard(message: Message):
    lang = lang_of(message.from_user.id)
    txt = build_rank_text(lang)
    await message.answer(txt if txt else T(lang, "rank_empty"))


@dp.message(Command("help"))
@dp.message(F.text.in_({TEXTS["zh"]["btn_help"], TEXTS["en"]["btn_help"]}))
async def show_help(message: Message):
    lang = lang_of(message.from_user.id)
    await message.answer(T(lang, "help_title"), reply_markup=help_menu(lang))


@dp.callback_query(F.data == "h_home")
async def help_home(cb: CallbackQuery):
    lang = lang_of(cb.from_user.id)
    await cb.message.edit_text(T(lang, "help_title"), reply_markup=help_menu(lang))
    await cb.answer()


@dp.callback_query(F.data == "h_tips")
async def help_tips(cb: CallbackQuery):
    lang = lang_of(cb.from_user.id)
    await cb.message.edit_text(T(lang, "tips_content", invite=INVITE_REWARD, min=WITHDRAW_MIN,
                                 channel=CHANNEL_LINK, group=GROUP_LINK),
                               reply_markup=back_menu(lang), parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "h_faq")
async def help_faq(cb: CallbackQuery):
    lang = lang_of(cb.from_user.id)
    await cb.message.edit_text(T(lang, "faq_content"), reply_markup=back_menu(lang), parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "h_support")
async def help_support(cb: CallbackQuery):
    lang = lang_of(cb.from_user.id)
    await cb.message.edit_text(T(lang, "support_content", contact=SUPPORT_CONTACT), reply_markup=back_menu(lang))
    await cb.answer()


def withdraw_view(user, lang):
    """生成兑换提现页的文字和按钮(整合绑定显示)。"""
    acct = user["account"] if user and user["account"] else "—"
    pts = user["points"] if user else 0
    rows = []
    if not user or not user["account"]:
        # 没绑定: 提示去绑定 + 绑定按钮
        status = T(lang, "withdraw_no_acct", min=WITHDRAW_MIN)
        rows.append([InlineKeyboardButton(text=T(lang, "btn_bind_now"), callback_data="wd_bind")])
    elif pts < WITHDRAW_MIN:
        # 已绑定但积分不够: 显示账号 + 修改按钮
        status = T(lang, "withdraw_not_enough", min=WITHDRAW_MIN)
        rows.append([InlineKeyboardButton(text=T(lang, "btn_bind_edit"), callback_data="wd_bind")])
    else:
        # 已绑定且够分: 兑换按钮 + 修改按钮
        status = ""
        rows.append([InlineKeyboardButton(text=T(lang, "withdraw_btn"), callback_data="confirm_withdraw")])
        rows.append([InlineKeyboardButton(text=T(lang, "btn_bind_edit"), callback_data="wd_bind")])
    rows.append([InlineKeyboardButton(text=T(lang, "help_back"), callback_data="h_home")])
    txt = T(lang, "withdraw_info", pts=pts, min=WITHDRAW_MIN, acct=acct, status=status)
    return txt, InlineKeyboardMarkup(inline_keyboard=rows)


# 主菜单"兑换提现"按钮(文字触发)
@dp.message(F.text.in_({TEXTS["zh"]["btn_withdraw"], TEXTS["en"]["btn_withdraw"]}))
async def withdraw_entry(message: Message):
    uid = message.from_user.id
    lang = lang_of(uid)
    user = get_user(uid)
    if not user:
        create_user(uid, message.from_user.username or "", message.from_user.first_name or "")
        user = get_user(uid)
    txt, kb = withdraw_view(user, lang)
    await message.answer(txt, reply_markup=kb, parse_mode="HTML")


# 兑换页里点"绑定/修改账号" → 进入绑定输入态
@dp.callback_query(F.data == "wd_bind")
async def wd_bind(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = lang_of(uid)
    user = get_user(uid)
    awaiting_bind.add(uid)
    txt = T(lang, "bind_ask")
    if user and user["account"]:
        txt += "\n\n" + T(lang, "bind_current", acct=user["account"])
    await cb.message.edit_text(txt, reply_markup=back_menu(lang), parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "confirm_withdraw")
async def confirm_withdraw(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = lang_of(uid)
    user = get_user(uid)
    # 再校验一次
    if not user or not user["account"] or user["points"] < WITHDRAW_MIN:
        await cb.answer()
        return
    # 显示绑定的平台账号, 让用户核对, 核对无误才真正扣分
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=T(lang, "withdraw_confirm_btn"), callback_data="do_withdraw")],
        [InlineKeyboardButton(text=T(lang, "help_back"), callback_data="h_home")]])
    await cb.message.edit_text(
        T(lang, "withdraw_confirm", acct=user["account"], min=WITHDRAW_MIN),
        reply_markup=kb, parse_mode="HTML")
    await cb.answer()


@dp.callback_query(F.data == "do_withdraw")
async def do_withdraw(cb: CallbackQuery):
    uid = cb.from_user.id
    lang = lang_of(uid)
    user = get_user(uid)
    # 二次校验, 防并发/重复点击
    if not user or not user["account"] or user["points"] < WITHDRAW_MIN:
        await cb.answer()
        return
    # 扣除门槛对应积分 (防止无限提现)
    set_field(uid, "points", user["points"] - WITHDRAW_MIN)
    await cb.message.edit_text(T(lang, "withdraw_done_deduct", min=WITHDRAW_MIN, contact=SUPPORT_CONTACT))
    await cb.answer()
    # 通知管理员处理打款
    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"💰 兑换提现申请\n"
                f"TG用户: {user['first_name']} (@{user['username']}) id={uid}\n"
                f"平台账号(UID): {user['account']}\n"
                f"兑换积分: {WITHDRAW_MIN}\n"
                f"剩余TG积分: {user['points']-WITHDRAW_MIN}\n\n"
                f"👉 请到平台给该UID加 {WITHDRAW_MIN} 积分")
        except Exception:
            pass


@dp.message(F.text & ~F.text.startswith("/"))
async def catch_text(message: Message):
    uid = message.from_user.id
    lang = lang_of(uid)
    user = get_user(uid)
    if not user:
        create_user(uid, message.from_user.username or "", message.from_user.first_name or "")
        user = get_user(uid)
    # 1) 正在等待绑定账号
    if uid in awaiting_bind:
        acct = message.text.strip()
        set_field(uid, "account", acct)
        awaiting_bind.discard(uid)
        await message.answer(T(lang, "bind_ok", acct=acct), reply_markup=main_menu(lang))
        # 绑定成功后直接显示兑换页, 用户可接着兑换
        user = get_user(uid)
        txt, kb = withdraw_view(user, lang)
        await message.answer(txt, reply_markup=kb, parse_mode="HTML")
        return
    # 2) 迁移口令 (不区分大小写)
    if message.text.strip().upper() == MIGRATION_CODE.upper():
        if user["code_claimed"] == 1:
            await message.answer(T(lang, "code_used"))
        else:
            set_field(uid, "points", (user["points"] or 0) + MIGRATION_BONUS)
            set_field(uid, "code_claimed", 1)
            await message.answer(T(lang, "code_ok", n=MIGRATION_BONUS), reply_markup=main_menu(lang))
        return
    # 3) 其它文本兜底
    await message.answer(T(lang, "fallback"), reply_markup=main_menu(lang))


def build_rank_text(lang):
    conn = db()
    rows = conn.execute("SELECT first_name,username,total_invites FROM users WHERE total_invites>0 ORDER BY total_invites DESC LIMIT 10").fetchall()
    conn.close()
    if not rows:
        return None
    medals = ["🥇", "🥈", "🥉"]
    lines = [T(lang, "rank_title")]
    for i, r in enumerate(rows):
        rank = medals[i] if i < 3 else f"{i+1}."
        name = r["first_name"] or (("@" + r["username"]) if r["username"] else "—")
        lines.append(T(lang, "rank_line", rank=rank, name=name, n=r["total_invites"]))
    lines.append(T(lang, "rank_foot"))
    return "\n".join(lines)


async def daily_rank_pusher():
    """每天到 RANK_PUSH_HOUR 点, 自动把邀请榜发到群 (中英双语各发一次)。"""
    from datetime import datetime
    if RANK_PUSH_HOUR < 0:
        return
    last_date = None
    while True:
        now = datetime.now()
        if now.hour == RANK_PUSH_HOUR and last_date != now.date():
            last_date = now.date()
            for lg in ("zh", "en"):
                txt = build_rank_text(lg)
                if txt:
                    try:
                        await bot.send_message(RANK_PUSH_CHAT, txt)
                    except Exception as e:
                        logging.warning(f"发榜失败: {e}")
        await asyncio.sleep(60)  # 每分钟检查一次


async def main():
    global BOT_USERNAME
    init_db()
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logging.info(f"机器人 @{BOT_USERNAME} 已启动")
    asyncio.create_task(daily_rank_pusher())   # 启动定时发榜
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
