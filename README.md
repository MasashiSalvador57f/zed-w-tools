# zed-w-tools

[Zed](https://zed.dev) エディタ向けの拡張機能です。
Rust で書かれ、WebAssembly (`wasm32-wasip2`) にコンパイルされて Zed 内で動作します。

## ディレクトリ構成

```
zed-w-tools/
├── extension.toml       # 拡張のメタデータ（id / name / version など）
├── Cargo.toml           # Rust クレート設定（cdylib としてビルド）
├── rust-toolchain.toml  # rustup 利用時に wasm32-wasip2 ターゲットを自動導入
└── src/
    └── lib.rs           # 拡張のエントリポイント（zed::Extension の実装）
```

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
