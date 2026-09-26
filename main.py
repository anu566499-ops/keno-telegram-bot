import random
import string
import sqlite3
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- CONFIGURATION ---
TOKEN = "8736253817:AAHrecOjOfdgxxSl2xMQWwRWRKZt7rNReaU"
ADMIN_ID = 8255824588
AGENT_PHONE = "0995877887"
WEBAPP_URL = "https://keno-telegram-bot-zfvg.onrender.com/game"

bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_NAME = "keno_house.db"

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_code TEXT UNIQUE,
            telegram_id INTEGER,
            amount REAL,
            txn_id TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_code TEXT UNIQUE,
            telegram_id INTEGER,
            amount REAL,
            phone_number TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def generate_ref(prefix="DEP"):
    return f"{prefix}-{ ''.join(random.choices(string.digits, k=4)) }"

def get_balance(telegram_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.0

def update_balance(telegram_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (telegram_id, balance) VALUES (?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET balance = balance + ?
    ''', (telegram_id, amount, amount))
    conn.commit()
    conn.close()


# --- TELEGRAM BOT INTERFACE ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Player"
    update_balance(user_id, 0.0)
    
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🎰 Play Keno Mini App", web_app=types.WebAppInfo(url=WEBAPP_URL)))
    builder.row(types.InlineKeyboardButton(text="💰 Deposit", callback_data="menu_deposit"),
                types.InlineKeyboardButton(text="💸 Withdraw", callback_data="menu_withdraw"))
    
    bal = get_balance(user_id)
    await message.answer(
        f"Welcome to Keno Casino 🎲\n\n"
        f"👤 Account: @{username}\n"
        f"💰 Ledger Balance: **{bal:.2f} ETB**", 
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "menu_deposit")
async def deposit_prompt(callback: types.CallbackQuery):
    ref_code = generate_ref("DEP")
    await callback.message.answer(
        f"📲 **Telebirr / CBE Deposit Instructions**\n\n"
        f"1. Send money to Agent Phone: `{AGENT_PHONE}`\n"
        f"2. Use this exact reference code in your transaction note/remark:\n\n"
        f"🔑 **Reference Code:** `{ref_code}`\n\n"
        f"After transferring, send your claim in this format:\n"
        f"`/deposit {ref_code} <Amount> <Txn_ID>`\n\n"
        f"*Example:* `/deposit {ref_code} 150 TXN84920192`"
    )
    await callback.answer()

@dp.message(Command("deposit"))
async def handle_deposit_claim(message: types.Message):
    args = message.text.split()
    if len(args) < 4:
        await message.reply("⚠️ Format error! Use: `/deposit DEP-1234 500 TXN12345678`")
        return
    
    ref_code, amount, txn_id = args[1].upper(), float(args[2]), args[3]
    user_id = message.from_user.id
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO deposits (ref_code, telegram_id, amount, txn_id) VALUES (?, ?, ?, ?)', 
                       (ref_code, user_id, amount, txn_id))
        conn.commit()
        conn.close()
    except sqlite3.IntegrityError:
        await message.reply("⚠️ That reference code was already used or exists. Open Deposit menu for a fresh code.")
        return
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="Approve ✅", callback_data=f"app_dep_{ref_code}_{user_id}_{amount}"),
        types.InlineKeyboardButton(text="Reject ❌", callback_data=f"rej_dep_{ref_code}")
    )
    await bot.send_message(
        ADMIN_ID, 
        f"🔔 **New Deposit Claim**\n\nRef: `{ref_code}`\nUser ID: `{user_id}`\nAmount: **{amount} ETB**\nTxn ID: `{txn_id}`", 
        reply_markup=builder.as_markup()
    )
    await message.reply(f"⏳ Claim `{ref_code}` submitted! Awaiting operator verification from {AGENT_PHONE}.")

@dp.callback_query(F.data.startswith("app_dep_"))
async def approve_deposit(callback: types.CallbackQuery):
    _, _, ref_code, user_id, amount = callback.data.split('_')
    update_balance(int(user_id), float(amount))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE deposits SET status = 'APPROVED' WHERE ref_code = ?", (ref_code,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(callback.message.text + "\n\n**STATUS: APPROVED ✅**")
    await bot.send_message(int(user_id), f"🎉 Your deposit (`{ref_code}`) of {amount} ETB has been approved and credited!")
    await callback.answer("Deposit approved successfully.")

@dp.callback_query(F.data.startswith("rej_dep_"))
async def reject_deposit(callback: types.CallbackQuery):
    ref_code = callback.data.split('_')[2]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE deposits SET status = 'REJECTED' WHERE ref_code = ?", (ref_code,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(callback.message.text + "\n\n**STATUS: REJECTED ❌**")
    await callback.answer("Deposit rejected.")

@dp.callback_query(F.data == "menu_withdraw")
async def withdraw_prompt(callback: types.CallbackQuery):
    await callback.message.answer(
        "💸 **Withdrawal Request**\n\n"
        "To cash out to your Telebirr/CBE account, reply with:\n"
        "`/withdraw <Amount> <Phone_Number>`\n\n"
        "*Example:* `/withdraw 300 0911223344`"
    )
    await callback.answer()

@dp.message(Command("withdraw"))
async def handle_withdrawal(message: types.Message):
    args = message.text.split()
    if len(args) < 3:
        await message.reply("⚠️ Format error! Use: `/withdraw 300 0911223344`")
        return
    
    amount, phone = float(args[1]), args[2]
    user_id = message.from_user.id
    current_bal = get_balance(user_id)
    
    if current_bal < amount:
        await message.reply(f"❌ Insufficient balance. You have {current_bal:.2f} ETB.")
        return
    
    update_balance(user_id, -amount)
    
    ref_code = generate_ref("WTH")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO withdrawals (ref_code, telegram_id, amount, phone_number) VALUES (?, ?, ?, ?)', 
                   (ref_code, user_id, amount, phone))
    conn.commit()
    conn.close()

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="Mark Paid & Closed ✅", callback_data=f"paid_wth_{ref_code}"),
        types.InlineKeyboardButton(text="Refund & Cancel ❌", callback_data=f"ref_wth_{ref_code}_{user_id}_{amount}")
    )
    await bot.send_message(
        ADMIN_ID,
        f"💸 **New Withdrawal Request**\n\nRef: `{ref_code}`\nUser ID: `{user_id}`\nAmount: **{amount} ETB**\nPhone: `{phone}`",
        reply_markup=builder.as_markup()
    )
    await message.reply(f"⏳ Withdrawal request `{ref_code}` registered. Processing within 24 hours.")

@dp.callback_query(F.data.startswith("paid_wth_"))
async def mark_withdrawal_paid(callback: types.CallbackQuery):
    ref_code = callback.data.split('_')[2]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE withdrawals SET status = 'PAID' WHERE ref_code = ?", (ref_code,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(callback.message.text + "\n\n**STATUS: PAID & COMPLETED ✅**")
    await callback.answer("Marked paid.")

@dp.callback_query(F.data.startswith("ref_wth_"))
async def refund_withdrawal(callback: types.CallbackQuery):
    _, _, ref_code, user_id, amount = callback.data.split('_')
    update_balance(int(user_id), float(amount))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE withdrawals SET status = 'REFUNDED' WHERE ref_code = ?", (ref_code,))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(callback.message.text + "\n\n**STATUS: REFUNDED ❌**")
    await bot.send_message(int(user_id), f"⚠️ Your withdrawal request (`{ref_code}`) was canceled and {amount} ETB has been refunded.")
    await callback.answer("Refunded balance to user.")


# --- LIFESPAN STARTUP FOR BOT POLLING ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    polling_task = asyncio.create_task(dp.start_polling(bot))
    yield
    polling_task.cancel()

app = FastAPI(lifespan=lifespan)


# --- MINI APP FRONTEND ROUTE ---
@app.get("/game", response_class=HTMLResponse)
def serve_game():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Atlas-V Keno Casino</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        :root {
            --bg-color: #0b131e;
            --panel-bg: #131c29;
            --accent-gold: #f39c12;
            --accent-green: #2ecc71;
            --accent-blue: #3498db;
            --text-main: #ffffff;
            --text-muted: #8a9ba8;
            --border-color: #213247;
        }
        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 10px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            width: 100%;
            max-width: 480px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            background: var(--panel-bg);
            padding: 12px 16px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
            font-size: 14px;
        }
        .main-layout {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        .keno-grid {
            display: grid;
            grid-template-columns: repeat(10, 1fr);
            gap: 4px;
            flex: 3;
            background: var(--panel-bg);
            padding: 8px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
        }
        .cell {
            background: #1c2b3c;
            border: 1px solid #2a3f58;
            border-radius: 4px;
            aspect-ratio: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
            cursor: pointer;
            user-select: none;
            transition: all 0.1s ease;
        }
        .cell.selected {
            background: var(--accent-gold);
            color: #000;
            border-color: #f1c40f;
            transform: scale(1.05);
        }
        .cell.hit {
            background: var(--accent-green) !important;
            color: #000;
            box-shadow: 0 0 8px var(--accent-green);
        }
        .cell.drawn {
            background: var(--accent-blue);
            color: #fff;
        }
        .sidebar-payout {
            flex: 1.2;
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 8px;
            font-size: 11px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .sidebar-payout h4 {
            margin: 0 0 5px 0;
            text-align: center;
            color: var(--accent-gold);
            font-size: 12px;
        }
        .payout-row {
            display: flex;
            justify-content: space-between;
            padding: 3px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .controls-panel {
            background: var(--panel-bg);
            padding: 12px;
            border-radius: 10px;
            border: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .bet-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .bet-input-group {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        input[type="number"] {
            background: #0b131e;
            border: 1px solid var(--border-color);
            color: white;
            padding: 8px;
            width: 70px;
            text-align: center;
            border-radius: 6px;
            font-size: 14px;
            font-weight: bold;
        }
        .action-btn {
            background: linear-gradient(135deg, #e74c3c, #c0392b);
            color: white;
            border: none;
            padding: 12px;
            font-size: 16px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
            width: 100%;
            text-transform: uppercase;
            box-shadow: 0 4px 10px rgba(231, 76, 60, 0.3);
        }
        .action-btn:active {
            transform: scale(0.98);
        }
        .action-btn:disabled {
            background: #4a5568;
            cursor: not-allowed;
            box-shadow: none;
        }
    </style>
</head>
<body>

    <div class="container">
        <!-- Top Status Bar -->
        <div class="header">
            <span>Balance: <strong id="balance" style="color: var(--accent-green);">0.00</strong> ETB</span>
            <span>Selected: <strong id="count">0</strong>/10</span>
        </div>

        <!-- Main Grid & Multiplier Sidebar Layout -->
        <div class="main-layout">
            <div class="keno-grid" id="grid"></div>
            
            <div class="sidebar-payout">
                <div>
                    <h4>Multiplier</h4>
                    <div id="payoutTableList">
                        <div class="text-muted" style="text-align:center; padding:10px 0;">Pick numbers to view table</div>
                    </div>
                </div>
                <div style="font-size:10px; color:var(--text-muted); text-align:center; margin-top:5px;">Atlas-V Style</div>
            </div>
        </div>

        <!-- Controls & Bet Panel -->
        <div class="controls-panel">
            <div class="bet-row">
                <span>Bet Amount (ETB):</span>
                <div class="bet-input-group">
                    <button onclick="adjustBet(-5)" style="padding:6px 10px; background:#213247; color:#fff; border:none; border-radius:4px; cursor:pointer;">-</button>
                    <input type="number" id="betAmount" value="10" min="1">
                    <button onclick="adjustBet(5)" style="padding:6px 10px; background:#213247; color:#fff; border:none; border-radius:4px; cursor:pointer;">+</button>
                </div>
            </div>
            <button class="action-btn" onclick="playKeno()" id="playBtn">START DRAW (20/80)</button>
        </div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        
        const userId = tg.initDataUnsafe?.user?.id || 999999; 
        let selectedNumbers = new Set();
        const gridEl = document.getElementById('grid');

        const multipliersRef = {
            1: {1: 3.0},
            2: {2: 9.0},
            3: {2: 1.0, 3: 26.0},
            4: {2: 2.0, 3: 5.0, 4: 70.0},
            5: {3: 3.0, 4: 12.0, 5: 300.0},
            10: {5: 2.0, 6: 15.0, 7: 50.0, 8: 200.0, 9: 1000.0, 10: 10000.0}
        };

        for (let i = 1; i <= 80; i++) {
            const cell = document.createElement('div');
            cell.className = 'cell';
            cell.id = `cell-${i}`;
            cell.innerText = i;
            cell.onclick = () => toggleCell(i);
            gridEl.appendChild(cell);
        }

        async function fetchBalance() {
            try {
                const res = await fetch(`/api/balance/${userId}`);
                const data = await res.json();
                document.getElementById('balance').innerText = data.balance.toFixed(2);
            } catch(e) { console.error(e); }
        }
        fetchBalance();

        function toggleCell(num) {
            const el = document.getElementById(`cell-${num}`);
            if (selectedNumbers.has(num)) {
                selectedNumbers.delete(num);
                el.classList.remove('selected');
            } else {
                if (selectedNumbers.size >= 10) { alert("Max 10 choices allowed"); return; }
                selectedNumbers.add(num);
                el.classList.add('selected');
            }
            document.getElementById('count').innerText = selectedNumbers.size;
            updatePayoutSidebar();
        }

        function adjustBet(amount) {
            const input = document.getElementById('betAmount');
            let val = parseInt(input.value) || 10;
            val = Math.max(1, val + amount);
            input.value = val;
        }

        function updatePayoutSidebar() {
            const count = selectedNumbers.size;
            const container = document.getElementById('payoutTableList');
            if (count === 0) {
                container.innerHTML = '<div style="text-align:center; color:#8a9ba8; padding:10px 0;">Pick numbers</div>';
                return;
            }
            const table = multipliersRef[count];
            if (!table) {
                container.innerHTML = '<div style="text-align:center; color:#8a9ba8; padding:10px 0;">Custom Pick</div>';
                return;
            }
            let html = '';
            for (let [hits, mult] of Object.entries(table)) {
                html += `<div class="payout-row"><span>${hits} Hits:</span><strong style="color:var(--accent-gold);">${mult}x</strong></div>`;
            }
            container.innerHTML = html;
        }

        async function playKeno() {
            if (selectedNumbers.size === 0) { alert("Pick at least 1 number!"); return; }
            const betAmount = parseFloat(document.getElementById('betAmount').value);
            document.getElementById('playBtn').disabled = true;

            document.querySelectorAll('.cell').forEach(c => c.classList.remove('hit', 'drawn'));

            try {
                const response = await fetch('/api/play', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_id: userId,
                        bet_amount: betAmount,
                        chosen_numbers: Array.from(selectedNumbers)
                    })
                });
                
                const result = await response.json();
                if (!response.ok) throw new Error(result.detail);

                result.drawn_numbers.forEach(num => {
                    const el = document.getElementById(`cell-${num}`);
                    if (selectedNumbers.has(num)) {
                        el.classList.add('hit');
                    } else {
                        el.classList.add('drawn');
                    }
                });

                document.getElementById('balance').innerText = result.new_balance.toFixed(2);
                if (result.payout > 0) {
                    setTimeout(() => alert(`🎉 Congratulations! Won ${result.payout.toFixed(2)} ETB (${result.hit_count} hits)`), 300);
                }
            } catch (err) {
                alert("Error: " + err.message);
            } finally {
                document.getElementById('playBtn').disabled = false;
            }
        }
    </script>
</body>
</html>
    """

# --- GAME ENGINE API ---
class GameBet(BaseModel):
    user_id: int
    bet_amount: float
    chosen_numbers: list[int]

@app.post("/api/play")
def play_keno(data: GameBet):
    current_bal = get_balance(data.user_id)
    if current_bal < data.bet_amount:
        raise HTTPException(status_code=400, detail="Insufficient internal ledger balance.")
    
    if not (1 <= len(data.chosen_numbers) <= 10):
        raise HTTPException(status_code=400, detail="Pick between 1 and 10 numbers.")

    update_balance(data.user_id, -data.bet_amount)

    drawn_numbers = random.sample(range(1, 81), 20)
    hits = [num for num in data.chosen_numbers if num in drawn_numbers]
    hit_count = len(hits)
    picked_count = len(data.chosen_numbers)

    payout_table = {
        1: {1: 3.0},
        2: {2: 9.0},
        3: {2: 1.0, 3: 26.0},
        4: {2: 2.0, 3: 5.0, 4: 70.0},
        5: {3: 3.0, 4: 12.0, 5: 300.0},
        10: {5: 2.0, 6: 15.0, 7: 50.0, 8: 200.0, 9: 1000.0, 10: 10000.0}
    }
    
    multiplier = payout_table.get(picked_count, {}).get(hit_count, 0.0)
    payout = data.bet_amount * multiplier

    if payout > 0:
        update_balance(data.user_id, payout)

    return {
        "drawn_numbers": drawn_numbers,
        "hits": hits,
        "hit_count": hit_count,
        "payout": payout,
        "multiplier": multiplier,
        "new_balance": get_balance(data.user_id)
    }

@app.get("/api/balance/{user_id}")
def get_user_balance_api(user_id: int):
    return {"balance": get_balance(user_id)}
