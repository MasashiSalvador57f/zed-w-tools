# zed-w-tools

[Zed](https://zed.dev) エディタ向けの拡張機能です。
Rust で書かれ、WebAssembly (`wasm32-wasip2`) にコンパイルされて Zed 内で動作します。

## ディレクトリ構成

```
zed-w-tools/
├── extension.toml       # 拡張のメタデータ（id / name / version / slash command 宣言）
├── Cargo.toml           # Rust クレート設定（cdylib としてビルド）
├── rust-toolchain.toml  # rustup 利用時に wasm32-wasip2 ターゲットを自動導入
├── src/
│   └── lib.rs           # 拡張のエントリポイント（zed::Extension の実装）
└── scripts/
    └── tategaki_preview.py  # 縦書きプレビュー HTML 生成スクリプト（lib.rs から include_str! で埋め込み）
```

## 機能

### `/tategaki-preview` — 日本語テキストの縦書きプレビュー

Assistant パネルのスラッシュコマンドとして提供します。
指定したテキストファイルを縦書きレイアウトの HTML に変換し、ブラウザで開きます。

```
/tategaki-preview <ファイル> [chars=40] [spacing=1.75] [lines=30] [font_size=16]
```

- ファイルパスはワークツリーからの相対パス、または絶対パス
- `chars`: 1行あたりの文字数（既定: 40）
- `spacing`: 行間（文字サイズ比、既定: 1.75）
- `lines`: 1ページあたりの行数（既定: 30）
- `font_size`: 文字サイズ px（既定: 16）

プレビュー画面上部のコントロールバーから各値をリアルタイムに変更でき、
「PDF出力」ボタンで A4 横サイズへの印刷（PDF保存）が可能です。

対応するカクヨム記法:

- `｜漢字《かんじ》` — 明示的なルビ
- `漢字《かんじ》` — 直前の漢字の連なりへのルビ
- `《《傍点》》` — 傍点（sesame dots）

実行には `python3` が必要です（PATH 上にあるものを自動検出します）。

## 開発環境の前提

Zed は拡張を `wasm32-wasip2` ターゲットでビルドします。
そのため **rustup 経由の Rust** が必要です。

```sh
# rustup が未導入の場合
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# wasm ターゲットを追加（rust-toolchain.toml があれば自動で入ります）
rustup target add wasm32-wasip2
```

> Homebrew の `rust` フォーミュラなど rustup を経由しない Rust では
> `wasm32-wasip2` ターゲットを追加できないため、Zed でのビルドに失敗します。

## ローカルでの動作確認（Dev Extension としてインストール）

1. Zed を起動し、コマンドパレット（`cmd-shift-p`）を開く
2. `zed: install dev extension` を実行
3. このリポジトリのディレクトリを選択

ビルドログは Zed のログ（`zed: open log`）で確認できます。
詳細なログが欲しい場合は `zed --foreground` で起動してください。

## 手元でのビルド確認

```sh
# 型チェックのみ（ホストターゲットで高速に確認）
cargo check

# Zed と同じターゲットでビルド
cargo build --release --target wasm32-wasip2
```

## 参考

- [Developing Extensions - Zed Docs](https://zed.dev/docs/extensions/developing-extensions)
- [zed_extension_api - crates.io](https://crates.io/crates/zed_extension_api)
