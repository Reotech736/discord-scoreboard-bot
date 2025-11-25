"""
Discord Scoreboard Bot (Two-Player, endless rounds)

Slash commands:
- /board_start  <player_a> <player_b> [title]
- /board_add    <a> <b>
- /board_edit   <round_no> [a] [b]
- /board_undo
- /board_show
- /board_rename [player_a] [player_b] [title]
- /board_reset
- /board_delete
- /board_zero_style <dash|zero>
- /board_help

Table spec:
- RND column width: 5 (right-justified, + one trailing space)
- Each player column width: 10
  - Player name: ASCII only, **8 chars right-justified**, with one space on both sides (total 10)
  - Scores: right-justified with **one trailing space** (total 10). When 0 → "-" if zero_as_dash=True, else "0"
- Σ totals, Δ differences (+/-)

Storage:
- Per channel/thread, saved to SCOREBOARD_PATH or ./scoreboards.json
"""

from __future__ import annotations
import os
import json
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env if present
except ImportError:
    pass  # python-dotenv not installed; skip .env loading
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional

import discord
from discord import app_commands

DATA_PATH = os.environ.get("SCOREBOARD_PATH", "scoreboards.json")

# ------------------ Persistence ------------------

def _load_all() -> Dict[str, dict]:
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def _save_all(data: Dict[str, dict]):
    tmp = DATA_PATH + ".tmp"
    os.makedirs(os.path.dirname(DATA_PATH) or ".", exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_PATH)

# Key = f"{guild_id}:{channel_id}:{thread_id_or_0}"
def _key(ctx: discord.Interaction) -> str:
    guild_id = ctx.guild_id or 0
    channel = ctx.channel
    thread_id = channel.id if isinstance(channel, discord.Thread) else 0
    parent_id = channel.parent_id if isinstance(channel, discord.Thread) else channel.id
    channel_id = parent_id
    return f"{guild_id}:{channel_id}:{thread_id}"

# ------------------ Model ------------------

@dataclass
class Round:
    a: int
    b: int

@dataclass
class Board:
    title: str
    player_a: str
    player_b: str
    rounds: List[Round] = field(default_factory=list)
    message_id: Optional[int] = None  # message to edit

    # 表示仕様
    COL_RND: int = 5
    COL_PLY: int = 10  # " " + 8 content + " "
    zero_as_dash: bool = True  # True: 0を"-"表示 / False: "0"表示

    # ---- formatting helpers ----
    @staticmethod
    def _is_ascii(s: str) -> bool:
        try:
            s.encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    @classmethod
    def _validate_name(cls, name: Optional[str]) -> Optional[str]:
        if name is None:
            return None
        if not cls._is_ascii(name):
            return None
        return name[:8]  # ASCII 8文字にトリム

    # ---- render ----
    def totals(self):
        ta = sum(r.a for r in self.rounds)
        tb = sum(r.b for r in self.rounds)
        return ta, tb

    def render(self) -> str:
        """Return a code-block string of the scoreboard in fixed layout."""
        COL_RND = self.COL_RND
        COL_PLY = self.COL_PLY

        def hline() -> str:
            return "+" + "-" * COL_RND + "+" + "-" * COL_PLY + "+" + "-" * COL_PLY + "+\n"

        # 名前: ASCII前提, 8文字右詰め, 両端スペースで幅10
        def fmt_name(name: str) -> str:
            safe = name.encode("ascii", "ignore").decode("ascii")
            s = safe[:8].rjust(8)
            return f" {s} "

        # RNDセル: 幅5、右詰め + 末尾スペース
        def fmt_rnd(text: str) -> str:
            return f"{text:>{COL_RND-1}} "

        # スコア: 右詰め + 末尾スペース / 0の見た目はフラグで切替
        def fmt_score_val(x: int) -> str:
            if x == 0:
                s = "-" if self.zero_as_dash else "0"
            else:
                s = str(x)
            return f"{s:>{COL_PLY-1}} "

        # Δ行は常に±付き（+0 / -0 はそのまま）
        def fmt_score_signed(x: int) -> str:
            s = f"{x:+d}"
            return f"{s:>{COL_PLY-1}} "

        ta, tb = self.totals()
        diff = ta - tb

        header = f"|{fmt_rnd('RND')}|{fmt_name(self.player_a)}|{fmt_name(self.player_b)}|\n"

        body_lines = []
        for i, r in enumerate(self.rounds, start=1):
            body_lines.append(f"|{fmt_rnd(str(i))}|{fmt_score_val(r.a)}|{fmt_score_val(r.b)}|")
        body = ("\n".join(body_lines) + "\n") if body_lines else ""

        footer = (
            f"|{fmt_rnd('Σ')}|{fmt_score_val(ta)}|{fmt_score_val(tb)}|\n"
            f"|{fmt_rnd('Δ')}|{fmt_score_signed(+diff)}|{fmt_score_signed(-diff)}|\n"
        )

        table = hline() + header + hline() + body + hline() + footer + hline()
        title = f"【{self.title}】 {self.player_a} vs {self.player_b}"
        return f"**{title}**\n```\n{table}```"

    @classmethod
    def from_dict(cls, d: dict) -> "Board":
        rounds = [Round(**r) for r in d.get("rounds", [])]
        return cls(
            title=d.get("title", "Scoreboard"),
            player_a=d.get("player_a", "PlayerA"),
            player_b=d.get("player_b", "PlayerB"),
            rounds=rounds,
            message_id=d.get("message_id"),
            COL_RND=d.get("COL_RND", 5),
            COL_PLY=d.get("COL_PLY", 10),
            zero_as_dash=d.get("zero_as_dash", True),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rounds"] = [asdict(r) for r in self.rounds]
        return d

# ------------------ Bot ------------------

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

def get_board(inter: discord.Interaction) -> Optional[Board]:
    data = _load_all()
    k = _key(inter)
    if k in data:
        return Board.from_dict(data[k])
    return None

def save_board(inter: discord.Interaction, board: Board):
    data = _load_all()
    data[_key(inter)] = board.to_dict()
    _save_all(data)

# ---- Commands ----

@tree.command(name="board_start", description="Start a new two-player scoreboard in this channel/thread")
@app_commands.describe(
    player_a="Left player name (ASCII, up to 8 chars; right-justified)",
    player_b="Right player name (ASCII, up to 8 chars; right-justified)",
    title="Optional title",
)
async def board_start(inter: discord.Interaction, player_a: str, player_b: str, title: Optional[str] = None):
    await inter.response.defer(thinking=True, ephemeral=True)

    va = Board._validate_name(player_a)
    vb = Board._validate_name(player_b)
    if va is None or vb is None:
        await inter.followup.send(
            "名前は **半角ASCIIのみ**（最大8文字）にしてください。全角は使用できません。\n"
            "例: `Reo`, `Haruna`, `Player01`",
            ephemeral=True,
        )
        return

    existing = get_board(inter)
    if existing and (existing.rounds or existing.message_id):
        await inter.followup.send("既にボードがあります。/board_show で確認、/board_reset で初期化できます。", ephemeral=True)
        return

    board = Board(title=title or "戦績ボード", player_a=va, player_b=vb, rounds=[])
    msg = await inter.channel.send(board.render())
    board.message_id = msg.id
    save_board(inter, board)
    await inter.followup.send("ボードを作成しました！以後は /board_add でラウンドを追加できます。", ephemeral=True)

@tree.command(name="board_add", description="Add a round: points for player_a and player_b (0 renders as '-' or '0')")
@app_commands.describe(a="Points for player A (left)", b="Points for player B (right)")
async def board_add(inter: discord.Interaction, a: int = 0, b: int = 0):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board or not board.message_id:
        await inter.followup.send("先に /board_start でボードを作成してください。", ephemeral=True)
        return
    board.rounds.append(Round(a=a, b=b))
    try:
        msg = await inter.channel.fetch_message(board.message_id)
        await msg.edit(content=board.render())
    except discord.NotFound:
        msg = await inter.channel.send(board.render())
        board.message_id = msg.id
    save_board(inter, board)
    await inter.followup.send(f"追加: RND {len(board.rounds)}  A={a}  B={b}", ephemeral=True)

@tree.command(name="board_edit", description="Edit an existing round score by its number")
@app_commands.describe(
    round_no="ラウンド番号 (1から始まる)",
    a="Player A の新しいスコア (未指定なら変更しない)",
    b="Player B の新しいスコア (未指定なら変更しない)",
)
async def board_edit(inter: discord.Interaction, round_no: int, a: Optional[int] = None, b: Optional[int] = None):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board or not board.rounds:
        await inter.followup.send("このチャンネルにはボードがありません。/board_start で作成してください。", ephemeral=True)
        return
    if round_no < 1 or round_no > len(board.rounds):
        await inter.followup.send(f"ラウンド {round_no} は存在しません。現在の最大ラウンドは {len(board.rounds)} です。", ephemeral=True)
        return

    r = board.rounds[round_no - 1]
    if a is not None:
        r.a = a
    if b is not None:
        r.b = b

    try:
        msg = await inter.channel.fetch_message(board.message_id)
        await msg.edit(content=board.render())
    except discord.NotFound:
        msg = await inter.channel.send(board.render())
        board.message_id = msg.id
    save_board(inter, board)
    await inter.followup.send(f"ラウンド {round_no} を修正しました。 A={r.a} B={r.b}", ephemeral=True)

@tree.command(name="board_undo", description="Remove the last round")
async def board_undo(inter: discord.Interaction):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board or not board.rounds:
        await inter.followup.send("取り消すラウンドがありません。", ephemeral=True)
        return
    board.rounds.pop()
    try:
        msg = await inter.channel.fetch_message(board.message_id)
        await msg.edit(content=board.render())
    except discord.NotFound:
        msg = await inter.channel.send(board.render())
        board.message_id = msg.id
    save_board(inter, board)
    await inter.followup.send("最後のラウンドを取り消しました。", ephemeral=True)

@tree.command(name="board_show", description="Show (re-render) the scoreboard")
async def board_show(inter: discord.Interaction):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board:
        await inter.followup.send("このチャンネルにはボードがありません。/board_start で作成してください。", ephemeral=True)
        return
    try:
        if board.message_id:
            msg = await inter.channel.fetch_message(board.message_id)
            await msg.edit(content=board.render())
            await inter.followup.send("ボードを更新しました。", ephemeral=True)
            return
    except discord.NotFound:
        pass
    msg = await inter.channel.send(board.render())
    board.message_id = msg.id
    save_board(inter, board)
    await inter.followup.send("ボードを再表示しました。", ephemeral=True)

@tree.command(name="board_rename", description="Rename both players and/or title")
@app_commands.describe(
    player_a="New name for player A (ASCII up to 8 chars; full-width not allowed)",
    player_b="New name for player B (ASCII up to 8 chars; full-width not allowed)",
    title="Optional new title",
)
async def board_rename(
    inter: discord.Interaction,
    player_a: Optional[str] = None,
    player_b: Optional[str] = None,
    title: Optional[str] = None,
):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board:
        await inter.followup.send("このチャンネルにはボードがありません。/board_start で作成してください。", ephemeral=True)
        return

    if player_a is not None:
        va = Board._validate_name(player_a)
        if va is None:
            await inter.followup.send("player_a は半角ASCIIのみ（最大8文字）。全角は不可です。", ephemeral=True)
            return
        board.player_a = va
    if player_b is not None:
        vb = Board._validate_name(player_b)
        if vb is None:
            await inter.followup.send("player_b は半角ASCIIのみ（最大8文字）。全角は不可です。", ephemeral=True)
            return
        board.player_b = vb
    if title:
        board.title = title

    try:
        msg = await inter.channel.fetch_message(board.message_id)
        await msg.edit(content=board.render())
    except discord.NotFound:
        msg = await inter.channel.send(board.render())
        board.message_id = msg.id
    save_board(inter, board)
    await inter.followup.send("名前/タイトルを更新しました。", ephemeral=True)

@tree.command(name="board_reset", description="Clear all rounds but keep names/title")
async def board_reset(inter: discord.Interaction):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board:
        await inter.followup.send("このチャンネルにはボードがありません。/board_start で作成してください。", ephemeral=True)
        return
    board.rounds.clear()
    try:
        msg = await inter.channel.fetch_message(board.message_id)
        await msg.edit(content=board.render())
    except discord.NotFound:
        msg = await inter.channel.send(board.render())
        board.message_id = msg.id
    save_board(inter, board)
    await inter.followup.send("ボードをリセットしました。", ephemeral=True)

@tree.command(name="board_delete", description="Delete the scoreboard entirely (remove message and data)")
async def board_delete(inter: discord.Interaction):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board:
        await inter.followup.send("このチャンネルにはボードがありません。", ephemeral=True)
        return

    # メッセージ削除
    if board.message_id:
        try:
            msg = await inter.channel.fetch_message(board.message_id)
            await msg.delete()
        except discord.NotFound:
            pass

    # JSONから削除
    data = _load_all()
    k = _key(inter)
    if k in data:
        del data[k]
        _save_all(data)

    await inter.followup.send("ボードを削除しました。/board_start で新規作成できます。", ephemeral=True)

@tree.command(name="board_zero_style", description="Choose how to display zeros (as '-' or '0')")
@app_commands.describe(style="表示方法: 'dash' なら '-'、'zero' なら '0'")
async def board_zero_style(inter: discord.Interaction, style: str):
    await inter.response.defer(thinking=True, ephemeral=True)
    board = get_board(inter)
    if not board:
        await inter.followup.send("このチャンネルにはボードがありません。/board_start で作成してください。", ephemeral=True)
        return

    if style.lower() == "dash":
        board.zero_as_dash = True
    elif style.lower() == "zero":
        board.zero_as_dash = False
    else:
        await inter.followup.send("style は 'dash' または 'zero' を指定してください。", ephemeral=True)
        return

    try:
        msg = await inter.channel.fetch_message(board.message_id)
        await msg.edit(content=board.render())
    except discord.NotFound:
        msg = await inter.channel.send(board.render())
        board.message_id = msg.id
    save_board(inter, board)

    await inter.followup.send(f"0 の表示方法を {'-' if board.zero_as_dash else '0'} に切り替えました。", ephemeral=True)

@tree.command(name="board_help", description="Show help for scoreboard commands")
async def board_help(inter: discord.Interaction):
    help_text = (
        "**Scoreboard Bot ヘルプ**\n\n"
        "利用できるコマンド一覧:\n"
        "• `/board_start <player_a> <player_b> [title]`\n"
        "　新しいスコアボードを開始します。名前は半角ASCII最大8文字（右詰め表示）。\n\n"
        "• `/board_add <a> <b>`\n"
        "　ラウンドを追加します。0 の表示は設定（'-' or '0'）。\n\n"
        "• `/board_edit <round_no> [a] [b]`\n"
        "　指定ラウンドのスコアを修正します。例: `/board_edit 3 a:50`\n\n"
        "• `/board_undo`\n"
        "　最後のラウンドを取り消します。\n\n"
        "• `/board_show`\n"
        "　スコアボードを再描画します。\n\n"
        "• `/board_rename [player_a] [player_b] [title]`\n"
        "　プレイヤー名やタイトルを変更します（名前はASCIIのみ/最大8文字）。\n\n"
        "• `/board_reset`\n"
        "　スコアをリセット（名前とタイトルは保持）。\n\n"
        "• `/board_delete`\n"
        "　スコアボードを完全に削除（メッセージとデータを消去）。\n\n"
        "• `/board_zero_style <dash|zero>`\n"
        "　0 の表示方法を切り替えます（`dash` → '-'、`zero` → '0'）。\n\n"
        "• `/board_help`\n"
        "　このヘルプを表示します。\n\n"
        "---\n"
        "**表示フォーマット**:\n"
        "- RND: 幅5（右詰め + 末尾スペース）\n"
        "- 名前列: 半角ASCII8文字を右詰め、両端スペースを含めて幅10\n"
        "- スコア列: 右詰め + 末尾スペース（幅10）。0 は設定に応じて '-' or '0'\n"
        "- Σ: 合計, Δ: 差分（±付き）\n"
    )
    await inter.response.send_message(help_text)

# ------------------ Client lifecycle ------------------

@client.event
async def on_ready():
    try:
        synced = await tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print("Sync error:", e)
    print(f"Logged in as {client.user}")

def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Please set DISCORD_TOKEN env var.")
    client.run(token)

if __name__ == "__main__":
    main()
