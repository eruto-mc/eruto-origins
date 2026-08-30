# -*- coding: utf-8 -*-
"""置いてある**ソース**と、いま配っている **jar** の中身を突き合わせる。

  py -3.12 tools/check_source_vs_released.py
  py -3.12 tools/check_source_vs_released.py --detail
  py -3.12 tools/check_source_vs_released.py --self-test

終了コード: 0 = 説明の付かない差が無い ／ 1 = 在る

## ⚠⚠ なぜ要るか

当部の規則（`.claude/rules/repos-and-git.md`）:

    ⚠⚠ **上流の枝の先頭でビルドしない**（2026-08-25 制定）。
      枝の先頭と、公開されている jar は別物。
      ⚠ `gradle.properties` の版の札だけでは見分けられなかった。

⚠ 既に在る `dev/verify/check_fork_jar_drift.py` は **jar 対 jar**——
⚠ **ビルドしてからでないと回せない**。
⚠⚠ **こちらは「ビルドする前」に同じ問いへ答える**（ソース 対 配っている jar）。

⚠ 実際に 2026-08-30 に1件つかまえた: `origins-classes` の submodule が
**枝の先頭**（`1354bc8`）に居て、配っている `1.2.1` の jar より **2 コミット先**だった。
⚠ 版の札は両方 `1.2.1` を名乗り、⚠ **上流に `1.2.1` のタグは無い**ので、
⚠ **中身を突き合わせる以外に見分ける手が無かった。**

## ⚠ 差の向きで意味が違う

| 向き | 意味 |
| - | - |
| ⚠⚠ **ソースだけに在る** | ⚠ **枝が先へ進んでいる**（危ない）か、⚠ **当部が包むときに消している**（MOR の 8 件） |
| **jar だけに在る** | ビルドで作られる物か、⚠ **枝が後ろに居る** |

⚠ **`data/` と `assets/` を分けて数える。**
⚠⚠ **Minecraft は `data/` の下を全部読む**ので、登録されない物を指す戦利品表・レシピ・進捗が
在るとそこで鳴く。⚠ `assets/`（絵・訳）は鳴かないので、**分けて出して人が決める**。

## ⚠ 許している分は、自分で一覧を持たない

MOR の 8 件は `dev/work/mor_patch/build_mor_patch.py` の `DROP` が正。
⚠⚠ **ここに写すと必ずずれる**ので、⚠ **あちらを読んで当てる**（読めなければ落ちる）。
"""
import argparse
import ast
import glob
import io
import os
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MC = r"c:\@projects\minecraft-club"
MODS = os.path.join(MC, "worlds", "world-3", "dev", "instance", "mods")
MOR_PATCH = os.path.join(MC, "worlds", "world-3", "dev", "work", "mor_patch",
                         "build_mor_patch.py")

# (submodule, 資源の置き場, 配っている jar の目印)
#   ⚠ jar は**版番号を書かない**（`check_power_refs.py` が版直書きで静かに落ちた・rule-misses 308）
CASES = [
    ("origins-classes", ["origins-classes/src/main/resources"], "origins-classes-forge-"),
    ("medieval", ["medieval/common/src/main/resources",
                  "medieval/forge/src/main/resources"], "Medieval Origins Revival-"),
    ("umbrellas", ["umbrellas/src/main/resources"], "origins_umbrellas-"),
]


def mor_drop():
    """MOR で当部が包むときに消している分を、`build_mor_patch.py` から読む。

    ⚠⚠ **写さない。** 一覧を2か所に置くとずれる。
    ⚠ 読めなければ**空ではなく例外**にする（空を返すと「許しが無い」＝鳴りっぱなしに化ける）。
    """
    with io.open(MOR_PATCH, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "DROP":
                    names = [ast.literal_eval(e) for e in node.value.elts]
                    return {"data/medievalorigins/powers/%s.json" % n for n in names}
    raise SystemExit("!! `DROP` を %s から読めない。⚠ 名前が変わったなら、ここも直す。" % MOR_PATCH)


def resolve_jar(key):
    hits = sorted(f for f in os.listdir(MODS)
                  if f.startswith(key) and f.endswith(".jar"))
    if len(hits) != 1:
        raise SystemExit("!! `%s` で始まる jar が %d 本（1本であるべき）: %s"
                         % (key, len(hits), ", ".join(hits) or "無し"))
    return os.path.join(MODS, hits[0])


def source_entries(roots):
    out = set()
    for rel in roots:
        base = os.path.join(REPO, rel.replace("/", os.sep))
        if not os.path.isdir(base):
            continue
        for b, _d, files in os.walk(base):
            for f in files:
                p = os.path.relpath(os.path.join(b, f), base).replace(os.sep, "/")
                if p.startswith(("data/", "assets/")):
                    out.add(p)
    return out


def jar_entries(path):
    with zipfile.ZipFile(path) as z:
        return {n for n in z.namelist()
                if n.startswith(("data/", "assets/")) and not n.endswith("/")}


def allowed_for(name):
    """その submodule で「ソースだけに在ってよい」もの。"""
    if name == "medieval":
        return mor_drop()
    return set()


def run(detail=False):
    ng = 0
    for name, roots, key in CASES:
        jarp = resolve_jar(key)
        src = source_entries(roots)
        jar = jar_entries(jarp)
        if not src:
            # ⚠⚠ 0 件は「差が無い」ではなく「読めていない」。必ず落とす。
            print("!! %-16s ソースの資源が 0 件 → **走査が壊れている**（%s）"
                  % (name, ", ".join(roots)))
            ng += 1
            continue

        allow = allowed_for(name)
        extra = src - jar
        unexplained = sorted(extra - allow)
        explained = sorted(extra & allow)
        missing = sorted(jar - src)

        d_un = [p for p in unexplained if p.startswith("data/")]
        a_un = [p for p in unexplained if p.startswith("assets/")]

        print("%-16s ソース %4d / jar %4d ／ 説明の付く差 %2d ／ ⚠ 付かない差 %2d"
              "（data %d・assets %d）／ jar だけ %d"
              % (name, len(src), len(jar), len(explained),
                 len(unexplained), len(d_un), len(a_un), len(missing)))
        print("                 （%s）" % os.path.basename(jarp))

        # ⚠ 許した分は**必ず件数と名前を出す**（黙って落とさない）。
        if explained:
            print("    許した分（当部が包むときに消している）:")
            for p in (explained if detail else explained[:3]):
                print("      - %s" % p)
            if not detail and len(explained) > 3:
                print("      … 他 %d 件（--detail で全部）" % (len(explained) - 3))

        for label, items in (("⚠⚠ data/", d_un), ("⚠ assets/", a_un),
                             ("jar だけ", missing)):
            if not items:
                continue
            print("    %s に説明の付かない差 %d 件:" % (label, len(items)))
            for p in (items if detail else items[:8]):
                print("      !! %s" % p)
            if not detail and len(items) > 8:
                print("      … 他 %d 件（--detail で全部）" % (len(items) - 8))

        if unexplained or missing:
            ng += 1
        print()

    print("判定: 説明の付かない差が在る submodule %d 件" % ng)
    if ng:
        print("⚠ **枝の先頭に居ないか確かめる。** 配っている jar が作られた点まで戻すか、")
        print("⚠ **差を当部の変更として説明できるようにしてからビルドする。**")
    return 1 if ng else 0


def self_test():
    """⚠ 陽性（壊せば鳴る）と陰性（いまは鳴らない）を両方置く。"""
    print("== 自己試験 ==")
    ng = 0

    drop = mor_drop()
    if len(drop) == 8:
        print("  ok `build_mor_patch.py` の DROP を 8 件読めた")
    else:
        print("  NG DROP が %d 件（8 件のはず）" % len(drop))
        ng += 1

    # ⚠ 陽性: 許し一覧を空にすると、MOR の 8 件が「説明の付かない差」に化けること。
    src = source_entries(["medieval/common/src/main/resources",
                          "medieval/forge/src/main/resources"])
    jar = jar_entries(resolve_jar("Medieval Origins Revival-"))
    if len(sorted(src - jar)) >= 8:
        print("  ok 陽性 許しを外すと MOR に差が %d 件見える" % len(src - jar))
    else:
        print("  NG 陽性 許しを外しても差が見えない（走査が壊れている）")
        ng += 1

    # ⚠ 陰性: 許しを当てれば 0 件になること。
    left = sorted((src - jar) - drop)
    if left:
        print("  NG 陰性 許しを当てても %d 件残る: %s" % (len(left), left[:5]))
        ng += 1
    else:
        print("  ok 陰性 許しを当てると MOR は 0 件")

    # ⚠ 陽性: でっち上げた目印の jar は「1本であるべき」で落ちること。
    try:
        resolve_jar("zzz-no-such-jar-")
        print("  NG 陽性 存在しない目印で落ちなかった")
        ng += 1
    except SystemExit:
        print("  ok 陽性 存在しない目印は落ちる")

    print("判定: NG %d 件" % ng)
    return 1 if ng else 0


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--detail", action="store_true", help="差を全部出す")
    a.add_argument("--self-test", action="store_true")
    ns = a.parse_args(argv)
    return self_test() if ns.self_test else run(detail=ns.detail)


if __name__ == "__main__":
    sys.exit(main())
