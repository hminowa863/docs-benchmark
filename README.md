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

## 期待回答なしでの手動評価

`questions.yaml` から `grading` を省略すると、正解や rubric を事前に用意せずに
実行できます。回答は run ごとの JSON に保存され、次のコマンドで比較できます。

```powershell
docsbench review SampleRepository
docsbench review SampleRepository --variant no-docs --question EXAMPLE-001
```

この場合 `report` の Accuracy は `—` になります。回答を確認してから
`grading` を追加し、同じ質問セットを再実行して自動採点へ移行できます。

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

`working_tree` は、対象リポジトリの現在の working tree から設定済みの
ドキュメントだけをコピーします。未コミットのドキュメント変更もベンチマークできます。

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
