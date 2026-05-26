# gadget

OBS Studio のブラウザソース等で使う「配信用小物」を管理するための最小 GTK4 プロセスランチャー。

各小物のディレクトリに `gadget.toml` を置いて `gadget <dir>` で起動する。起動・停止ボタンと
ログウィンドウを備えた小さな GUI が立ち上がり、小物本体はサブプロセスとして裏で動く。

## インストール

```
make install
```

`~/.local/bin/gadget` にインストールされる。

### 依存ライブラリ

| パッケージ | 用途 |
|---|---|
| PyGObject (`dev-python/pygobject`) | GTK4 バインディング |
| keyutils (`dev-python/keyutils`) | カーネルキーリング |

## gadget.toml

```toml
name = "My Gadget"                        # ウィンドウタイトル（必須）
exec = ["python", "-u", "main.py"]        # 起動コマンド（必須、dir からの相対）

[[keyring]]                               # カーネルキーリングのチェック（複数可、省略可）
key  = "my_secret_key"                    # キー名
desc = "API キーを入力してください。"      # パスワードダイアログの説明文

[info]                                    # ウィンドウ内に表示する補足情報（省略可）
markup = '<a href="http://localhost:8080/">http://localhost:8080/</a>'
```

### `exec`

文字列でも配列でも指定できる。`dir` をカレントディレクトリとして実行される。

```toml
exec = "python -u main.py"          # 文字列（空白で分割）
exec = ["python", "-u", "main.py"]  # 配列（推奨）
```

### `[[keyring]]`

起動ボタンを押したとき、リストの順にカーネルキーリングを確認する。キーが登録されていない場合は
パスワード入力ダイアログを表示し、入力値を `keyctl padd user <key> @u` でキーリングに登録してから
プロセスを起動する。

### `[info]`

`markup` フィールドに [Pango マークアップ](https://docs.gtk.org/Pango/pango_markup.html) を記述する。
`<a href="...">` リンクはクリックでブラウザが開く。

```toml
[info]
markup = 'ポート <b>8742</b> / <a href="http://localhost:8742/">Ticker</a> · <a href="http://localhost:8743/">Admin</a>'
```

## .desktop ファイルのインストール

`--install` オプションで `~/.local/share/applications/<dir>.desktop` を自動生成する。

```bash
gadget --install ~/projects/my-gadget
```

`gadget.toml` の `name`・`icon`・`comment` から内容を組み立て、`StartupWMClass` も自動設定されるので
手書きは不要。再実行で上書き更新できる。

### `comment` フィールド（任意）

```toml
comment = "Description shown in app launcher"
```

### `categories` フィールド（任意）

[freedesktop.org の仕様](https://specifications.freedesktop.org/menu-spec/latest/category-registry.html)
に基づくカテゴリ文字列。省略時は `AudioVideo`。

```toml
categories = "AudioVideo;Video;"
```

## 新しい小物の追加手順

1. 小物のプロジェクトディレクトリに `gadget.toml` を作成
2. SVG アイコンを作成（任意）
3. `gadget --install <dir>` を実行

## エージェント向け: ガジェット化の手順

AIエージェントがプロジェクトをガジェット化する際の手順。

### 1. ソースコードを読んで以下を把握する

- **起動コマンド**: メインスクリプトのファイル名とインタプリタ（`python`/`python3` など）。
  標準出力をリアルタイムにキャプチャするため `-u` フラグを付ける。
- **キーリングキー名**: `keyutils.request_key()`・`keyctl` の呼び出し箇所を探し、
  引数として渡されているキー名の文字列リテラルをすべて列挙する。
- **URL/ポート**: HTTPサーバーや WebSocket サーバーが使うポート番号。

### 2. `gadget.toml` を作成する

上記セクションの書式に従って `<dir>/gadget.toml` を作成する。

### 3. SVGアイコンを作成する（任意）

- プログラムの用途や配色から連想できる図案があれば `<dir>/icon.svg` として作成し、
  `gadget.toml` に `icon = "icon.svg"` を追記する。
- 図案化が難しい、またはアイコン制作能力がない場合はアイコンなしで進め、
  その旨をユーザーに伝える。

### 4. `.desktop` ファイルを登録する

```bash
$HOME/.local/bin/gadget --install <dir>
```

`~/.local/bin` が PATH に入っていない環境ではフルパスで呼ぶ。
