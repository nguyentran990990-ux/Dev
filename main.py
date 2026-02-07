import os, re, time, json, asyncio, random
from collections import defaultdict, deque
from dotenv import load_dotenv
from pyrogram import Client, filters
import httpx

# ================= ENV =================
load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION_NAME", "matrix")
ADMIN_LOG_GROUP = int(os.getenv("ADMIN_LOG_GROUP"))
MODE = os.getenv("MODE", "NORMAL")  # OFF | NORMAL | PARANOID

app = Client(SESSION, api_id=API_ID, api_hash=API_HASH)

# ================= LOAD BLOCK =================
with open("hard_block.json", encoding="utf-8") as f:
    HARD = json.load(f)

ABUSE_WORDS = set(
    HARD.get("abuse", []) +
    HARD.get("abuse_words", []) +
    HARD.get("sexual", []) +
    HARD.get("sexual_words", [])
)
ABUSE_REGEX = [re.compile(p, re.I) for p in HARD.get("regex", []) + HARD.get("abuse_patterns", [])]

# ================= DATA =================
strikes = defaultdict(int)
flood = defaultdict(deque)
last_text = {}
last_reply = {}
pending_reply = {}

MAX_STRIKE = 2
AUTO_REPLY_DELETE = 180  # giây
FAKE_DELAY = (1.2, 2.8)

SAFE_BOTS = {
    777000,      # Telegram
}

BAD_BOT_KEYWORDS = [
    "airdrop", "claim", "bonus", "free", "click",
    "verify", "wallet", "earn", "profit"
]

BOSS_PROFILE = """🔴 STATUS: BUSY

🤖 ToroAI — trợ lý tự động
⚠️ Boss hiện đang bận, vui lòng để lại nội dung
⚡ Tin nhắn hợp lệ sẽ được phản hồi sớm

── PORTAL ──
🌐 chienvnd.com.vn
📡 @ChienMatrix
☠️ @Chiendollar

—
Cᵛⁿ ChienMatrix ⚡️☠️
"""


# ================= UTILS =================
def now(): return time.time()

async def fake_delay():
    await asyncio.sleep(random.uniform(*FAKE_DELAY))

async def safe_send(chat_id, text):
    try:
        await app.send_message(chat_id, text)
    except:
        pass

async def report(action, uid, detail=""):
    await safe_send(
        ADMIN_LOG_GROUP,
        f"""🛡 MATRIX REPORT
🔔 {action}
👤 {uid}
📝 {detail}
⏱ {time.ctime()}"""
    )

def has_abuse(text: str) -> bool:
    t = text.lower()
    if any(w in t for w in ABUSE_WORDS):
        return True
    return any(r.search(t) for r in ABUSE_REGEX)

def detect_flood(uid):
    q = flood[uid]
    q.append(now())
    while q and now() - q[0] > 4:
        q.popleft()
    return len(q) >= 3

def detect_copy(uid, text):
    if last_text.get(uid) == text:
        return True
    last_text[uid] = text
    return False

async def is_scam(uid):
    async with httpx.AsyncClient(timeout=2) as c:
        try:
            r = await c.get(f"https://api.cas.chat/check?user_id={uid}")
            return r.json().get("ok", False)
        except:
            return False

def is_bad_bot(text):
    t = text.lower()
    return any(k in t for k in BAD_BOT_KEYWORDS)

async def kill(message, reason):
    uid = message.from_user.id
    try:
        await message.delete()
        await fake_delay()
        await app.block_user(uid)
        await app.delete_chat(uid, delete_history=True)
    except:
        pass
    await report("KILL", uid, reason)

# ================= HANDLER =================
@app.on_message(filters.private & ~filters.me)
async def guard(_, message):
    user = message.from_user
    if not user:
        return

    uid = user.id
    text = (message.text or message.caption or "").strip()
    if not text:
        return

    # ===== BOT =====
    if user.is_bot:
        if uid in SAFE_BOTS:
            return
        if is_bad_bot(text):
            await kill(message, "BAD_BOT")
        else:
            await report("BOT_SAFE", uid, "Theo dõi")
        return

    # ===== SCAM DB =====
    if await is_scam(uid):
        await kill(message, "SCAM_DB")
        return

    # ===== COPY / USERBOT =====
    if detect_copy(uid, text):
        await kill(message, "COPY_SPAM")
        return

    # ===== ABUSE / FLOOD =====
    violation = False
    reasons = []

    if has_abuse(text):
        violation = True
        reasons.append("ABUSE")

    if detect_flood(uid):
        violation = True
        reasons.append("FLOOD")

    if MODE == "OFF":
        violation = False

    if violation:
        strikes[uid] += 1
        try:
            await message.delete()
        except:
            pass

        await report("DELETE", uid, f"{reasons} | {strikes[uid]}")

        if strikes[uid] >= MAX_STRIKE:
            await kill(message, "MAX_STRIKE")
        return

    # ===== AUTO REPLY =====
    if uid not in last_reply or now() - last_reply[uid] > 86400:
        if uid not in pending_reply:
            pending_reply[uid] = asyncio.create_task(auto_reply(uid))

async def auto_reply(uid):
    await asyncio.sleep(5)
    try:
        msg = await app.send_message(uid, PROFILE_TEXT)
        last_reply[uid] = now()
        await report("AUTO_REPLY", uid)
        await asyncio.sleep(AUTO_REPLY_DELETE)
        await msg.delete()
    except:
        pass
    pending_reply.pop(uid, None)

# ================= START =================
print("🛡 MATRIX USERBOT RUNNING 24/7")
app.run()
