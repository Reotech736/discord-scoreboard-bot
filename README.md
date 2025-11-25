# Discord Scoreboard Bot

2人対戦のスコアボードを管理するDiscord Bot。ラウンドごとのスコアを記録し、合計点と点差を表示します。

## 機能

- チャンネル/スレッドごとにスコアボードを管理
- ラウンド追加、編集、削除機能
- 0の表示形式切り替え（`-` または `0`）
- スコアデータの永続化

## スラッシュコマンド

- `/board_start <player_a> <player_b> [title]` - 新しいスコアボードを開始
- `/board_add <a> <b>` - 新しいラウンドを追加
- `/board_edit <round_no> [a] [b]` - 特定のラウンドを編集
- `/board_undo` - 最後のラウンドを削除
- `/board_show` - 現在のスコアボードを表示
- `/board_rename [player_a] [player_b] [title]` - プレイヤー名やタイトルを変更
- `/board_reset` - 全ラウンドをクリア（プレイヤー名は維持）
- `/board_delete` - スコアボードを完全に削除
- `/board_zero_style <dash|zero>` - 0の表示方法を切り替え
- `/board_help` - ヘルプを表示

## セットアップ

### 必要なもの

- Python 3.8以上
- Discord Bot Token

### インストール

1. リポジトリをクローン:
```bash
git clone https://github.com/Reotech736/discord-scoreboard-bot.git
cd discord-scoreboard-bot
```

2. 仮想環境を作成（推奨）:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# または
.venv\Scripts\activate  # Windows
```

3. 必要なパッケージをインストール:
```bash
pip install discord.py python-dotenv
```

4. 環境変数を設定:

`.env` ファイルを作成し、Discord Bot Tokenを設定:
```
DISCORD_TOKEN=your_discord_bot_token_here
```

オプション: スコアボードデータの保存場所を変更する場合:
```
SCOREBOARD_PATH=/path/to/scoreboards.json
```

### 実行

```bash
python discord-scoreboard-bot.py
```

## 表示フォーマット

- **RND列**: 幅5（右詰め + 末尾スペース）
- **名前列**: ASCII文字8文字まで、右詰め、両端スペースを含めて幅10
- **スコア列**: 右詰め + 末尾スペース（幅10）、0は設定に応じて `-` または `0`
- **Σ**: 合計点
- **Δ**: 点差（±付き）

## データ保存

スコアボードデータは `scoreboards.json` に保存されます（デフォルト）。
各チャンネル/スレッドごとに個別のスコアボードが保存されます。
