# DocsBench

[English README](README.en.md)

DocsBench は、ドキュメントのバリエーションが Coding Agent の正確性、
コンテキスト消費量、検索行動に与える影響を測定するツールです。固定した
コードリビジョンを隔離 Git worktree に展開し、指定したドキュメントだけを
上書きしたうえで、質問ごとに新しい Agent プロセスを起動します。

## はじめに

```powershell
python -m pip install -e .
docsbench run SampleRepository --variant no-docs --variant current-docs
docsbench report SampleRepository
```

対象リポジトリの定義は `targets/<name>/target.yaml`、質問は同じ場所の
`questions.yaml` に配置します。実行結果は質問・バリエーションごとに 1 件の
JSON として `results/<name>/runs/` に保存され、集計結果は `summary.csv` に出力されます。

組み込みの `codex` アダプターは `codex exec --json` を呼び出し、JSONL の
イベントから回答、トークン使用量、コマンド実行を取得します。安全に動作確認
したい場合は `--agent mock` を使用してください。Rubric 形式の質問は既定では
未採点として保存されます。`--rubric-agent codex` を指定すると、候補回答と
採点基準だけを渡す独立した Codex プロセスで採点できます。

`report` の `input equiv.` は、cached input token を通常 input token の 1/10 として
換算した値です。実際の入力トークン総数は CSV の `*_input_tokens`、cached 分は run
JSON の `cached_input_tokens` で確認できます。

## 期待回答なしでの手動評価

`questions.yaml` から `grading` を省略すると、正解や rubric を事前に用意せずに
実行できます。回答は run ごとの JSON に保存され、次のコマンドで比較できます。

```powershell
docsbench review SampleRepository
docsbench review SampleRepository --variant no-docs --question EXAMPLE-001
```

この場合 `report` の Accuracy は `—` になります。回答を確認してから
`grading` を追加し、同じ質問セットを再実行して自動採点へ移行できます。

## 読み込み経路の比較

`trace` は、各 run で観測した検索・ファイル読取を実行順に表示します。variant と
質問を絞れば、同じ質問でどのドキュメントやソースへ到達したかを比較できます。

```powershell
docsbench trace ts-piper-wireless --question TSPW-007
docsbench trace ts-piper-wireless --variant before-docs --variant after-docs --question TSPW-007
```

集計の token と時間を中央値ではなく平均値で表示する場合は、`report --average`
を使用します。

```powershell
docsbench report ts-piper-wireless --average
```

## CodeGraph の初期化

各 variant で有効化できます。Agent を起動する前に該当 benchmark worktree で
`codegraph init` を実行するため、インデックスにはその variant のドキュメントが適用された
状態が使われます。CodeGraph CLI が `PATH` 上に必要です。

```yaml
variants:
  - name: codegraph
    codegraph:
      init: true
```

このように `type` を省略した variant は、固定 `code_ref` のドキュメントをそのまま使います。
既存の docs variant に CodeGraph を組み合わせる場合は、その `type` と `ref` に加えて
`codegraph.init` を指定してください。

すべての variant で一回限り有効化する場合は、`--codegraph-init` も使用できます。

```powershell
docsbench run ts-piper-wireless --variant after-docs --codegraph-init
```

## 対象リポジトリの設定

```yaml
name: SampleRepository
repository: ../SampleRepository
code_ref: main
docs:
  paths: [AGENTS.md, README.md, docs/**]
variants:
  - name: no-docs
    type: remove
  - name: current-docs
    type: git
    ref: main
```

`variants[].type` には次を指定できます。既定ではコードは `code_ref` に固定され、
`docs.paths` に一致するファイルだけが対象です。

| `type` | `ref` | ドキュメントの扱い |
| --- | --- | --- |
| `remove` | 不要 | 対象のドキュメントを worktree から削除する。 |
| `git` | 必須 | 指定した Git ref のドキュメントを worktree に上書きする。 |
| `working_tree` | 不要 | 対象リポジトリで現在チェックアウトされている作業ディレクトリからコピーする。未 commit の README や `docs/` の編集も評価できる。 |
| `baseline` | 不要 | overlay を適用せず、`code_ref` 時点のドキュメントを使う。`type` を省略した場合の既定値。 |

`scope` は適用範囲を指定します。既定値の `scope: docs` は、`docs.paths` に一致する
ファイルだけを対象にします。`git` variant で指定した `ref` からドキュメントだけを
上書きする場合は、明示的に `scope: docs` と書くこともできます。

```yaml
variants:
  - name: before-docs
    type: git
    ref: 69791c3ac62f12691fd6fbac120a4fb567591816
    scope: docs
```

コミット時点のリポジトリ全体（コード、ドキュメント、submodule の revision を含む）を
比較する場合は、`git` variant に `scope: repository` を指定します。この場合、指定した
`ref` が worktree 全体に使われ、結果 JSON の `code_commit` もその commit になります。

```yaml
variants:
  - name: before-change
    type: git
    ref: 69791c3ac62f12691fd6fbac120a4fb567591816
    scope: repository
```

## Submodule

worktree の作成後、submodule は `git submodule update --init --recursive` で
再帰的に初期化されます。`docs.paths` に submodule 配下のパスを含めれば、その
submodule 内のドキュメントにも overlay が適用されます。

```yaml
docs:
  paths:
    - README.md
    - vendor/library/docs/**
```

結果 JSON の `submodules` には、各 submodule の固定コード commit と、利用した
docs source commit が記録されます。`working_tree` バリアントで submodule の docs
を使う場合は、対象リポジトリ側でも当該 submodule を初期化しておいてください。
