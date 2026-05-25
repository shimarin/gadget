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

## .desktop ファイル

`~/.local/share/applications/` に配置することでアプリケーションランチャーから起動できる。
アイコンは SVG をプロジェクトディレクトリに置いて絶対パスで参照する。

```ini
[Desktop Entry]
Type=Application
Name=My Gadget
Comment=説明文
Exec=/home/shimarin/.local/bin/gadget /home/shimarin/projects/my-gadget
Terminal=false
Icon=/home/shimarin/projects/my-gadget/icon.svg
StartupWMClass=com.walbrix.gadget.my_gadget
Categories=AudioVideo;
```

`StartupWMClass` はデスクトップ環境が実行中ウィンドウと `.desktop` ファイルを紐付けるためのキーで、
タスクバーや起動中アイコンの表示に使われる。gadget はディレクトリ名の英数字以外を `_` に置換した値を
`application_id` として使うため、`com.walbrix.gadget.<sanitized_dir_name>` を指定する。

例: ディレクトリ名 `my-gadget` → `StartupWMClass=com.walbrix.gadget.my_gadget`

## 新しい小物の追加手順

1. 小物のプロジェクトディレクトリに `gadget.toml` を作成
2. SVG アイコンを作成（任意）
3. `~/.local/share/applications/<name>.desktop` を作成
