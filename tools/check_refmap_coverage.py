# -*- coding: utf-8 -*-
"""⚠⚠ **ソースの注釈が要求する参照が、refmap に載っているか**を突き合わせる。

  py -3.12 tools/check_refmap_coverage.py                 … 建てた apoli を見る
  py -3.12 tools/check_refmap_coverage.py --jar <jar>     … 好きな jar を見る
  py -3.12 tools/check_refmap_coverage.py --self-test     … 陽性・陰性の対照

終了コード: 0 = 欠けが無い ／ 1 = 在る

## ⚠⚠ なぜ要るか（2026-09-01・依頼者のクライアントを落とした）

⚠ ソースから建てた apoli を混ぜて配ったら、⚠⚠ **クライアントが起動時に落ちた**:

    Mixin apply failed apoli.mixins.json:GameRendererMixin
      @WrapOperation annotation on modifySubmersionType
      could not find any targets matching 'getFov'

⚠ 原因は refmap の欠け。⚠ **Mixin 0.8.5 の注釈処理は `@WrapOperation` を知らない。**
`mixinextras-common` が同梱している注釈処理を **`annotationProcessor` に載せて初めて**、
Mixin 本体の注釈処理に登録され、その `method=` と `@At(target=)` が refmap へ書かれる。

⚠⚠ **class の比較ではすり抜ける**——refmap は class ではない。
⚠ 実際、段2 の判定（`compare_with_released.py`）は**差を検出していた**のに、
⚠⚠ **許しの表が `apoli.refmap.json` を丸ごと通していた**（理由は「並びが変わる」）。

## ⚠ 見るもの

ソースの MixinExtras の注入注釈から、⚠ **refmap に載っているべき参照**を集める:

  * `method = "..."`        … 当てる先のメソッド（⚠ **記述子ごとが鍵**）
  * `@At(target = "...")`   … 注入点の当て先

⚠ それが refmap の `mappings` と `data.searge` の両方に在るかを見る
（⚠ **Forge の実行時が見るのは `data.searge`**）。

## ⚠ 取りこぼしやすい所（`projects-70` が試作で2回踏んだ）

  1. ⚠ `method = "render(Lnet/…;…)V"` は**記述子ごと**が鍵。`(` で切ると当たらない
  2. ⚠ `@Mixin(targets = "com.unascribed.ears.…")` は**他所の MOD のクラス**で難読化されない。
     その `method=` は refmap に無いのが正しい（`@At` の当て先が Minecraft ならそちらは要る）
  3. ⚠ 注釈の引数は**括弧を数えて**採る。`.*?` は `(I)Z` の括弧で切れる
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SRC = os.path.join(REPO, "apoli", "src", "main", "java")
BUILT = os.path.join(REPO, "apoli", "build", "libs")
MODS = r"c:\@projects\minecraft-club\worlds\world-3\dev\instance\mods"
RELEASED = os.path.join(MODS, "origins-forge-1.20.1-1.10.0.9-all-eruto1.jar")

# ⚠ MixinExtras の注入注釈。⚠ **Mixin 本体はこれらを知らない**ので、
#   `mixinextras-common` を `annotationProcessor` に載せないと refmap に載らない。
MIXINEXTRAS = ("WrapOperation", "ModifyExpressionValue", "ModifyReceiver",
               "ModifyReturnValue", "WrapWithCondition", "WrapMethod")


def args_of(text, start):
    """`(` から始まる注釈の引数を、⚠ **括弧を数えて**採る（`.*?` は記述子で切れる）。"""
    i = text.find("(", start)
    if i < 0:
        return ""
    depth, j, instr = 0, i, False
    while j < len(text):
        c = text[j]
        if c == '"' and text[j - 1] != "\\":
            instr = not instr
        elif not instr:
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return text[i + 1:j]
        j += 1
    return ""


def strings_for(key, block):
    """`key = "..."` と `key = {"...","..."}` の両方から文字列を採る。"""
    out = []
    m = re.search(r'\b%s\s*=\s*' % key, block)
    if not m:
        return out
    rest = block[m.end():].lstrip()
    if rest.startswith("{"):
        end = rest.find("}")
        out += re.findall(r'"((?:[^"\\]|\\.)*)"', rest[:end if end > 0 else len(rest)])
    else:
        m2 = re.match(r'"((?:[^"\\]|\\.)*)"', rest)
        if m2:
            out.append(m2.group(1))
    return out


def scan_sources():
    """ソースから (mixin クラスの内部名 → 要求する参照の集合) を作る。"""
    want = {}
    for dp, _dn, fs in os.walk(SRC):
        for f in fs:
            if not f.endswith(".java"):
                continue
            p = os.path.join(dp, f)
            with io.open(p, encoding="utf-8", errors="replace") as fh:
                t = fh.read()
            if not any(("@" + a) in t for a in MIXINEXTRAS):
                continue
            rel = os.path.relpath(p, SRC).replace(os.sep, "/")[:-len(".java")]
            # ⚠ `@Mixin(targets = "...")` は**他所の MOD のクラス**＝難読化されない
            mx = re.search(r"@Mixin\s*\(", t)
            foreign = False
            if mx:
                a = args_of(t, mx.start())
                tg = strings_for("targets", a)
                foreign = bool(tg) and not any(x.startswith("net.minecraft") for x in tg)
            need = set()
            for ann in MIXINEXTRAS:
                for m in re.finditer(r"@%s\s*\(" % ann, t):
                    block = args_of(t, m.start())
                    if not foreign:
                        # ⚠ **記述子ごとが鍵**（`(` で切らない）
                        need |= set(strings_for("method", block))
                    for at in re.finditer(r"@At\s*\(", block):
                        ab = args_of(block, at.start())
                        for tgt in strings_for("target", ab):
                            # ⚠ 当て先が Minecraft なら、他所当ての mixin でも要る
                            if not foreign or "net/minecraft" in tgt:
                                need.add(tgt)
            if need:
                want[rel] = need
    return want


def refmaps_of(jar):
    """jar（入れ子も辿る）から apoli の refmap を採る。返り値: (名前, 中身)。"""
    def dig(z, label):
        for n in z.namelist():
            if n.endswith("refmap.json") and "apoli" in n:
                return "%s ▸ %s" % (label, n), json.loads(z.read(n).decode("utf-8-sig"))
        for n in z.namelist():
            if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                with zipfile.ZipFile(io.BytesIO(z.read(n))) as iz:
                    got = dig(iz, "%s ▸ %s" % (label, os.path.basename(n)))
                    if got:
                        return got
        return None
    with zipfile.ZipFile(jar) as z:
        got = dig(z, os.path.basename(jar))
    if not got:
        raise SystemExit("!! %s に apoli の refmap が無い" % jar)
    return got


def missing(jar, want):
    """refmap に載っていない参照を数える。返り値: [(クラス, 参照, どちらの表に無いか)]"""
    name, d = refmaps_of(jar)
    mp = d.get("mappings", {})
    sg = d.get("data", {}).get("searge", {})
    out = []
    for cls, need in sorted(want.items()):
        for ref in sorted(need):
            in_mp = ref in mp.get(cls, {})
            in_sg = ref in sg.get(cls, {})
            if not (in_mp and in_sg):
                where = []
                if not in_mp:
                    where.append("mappings")
                if not in_sg:
                    where.append("data.searge")   # ⚠ 実行時が見るのはこちら
                out.append((cls, ref, "／".join(where)))
    return name, out


def default_jar():
    hits = sorted(f for f in os.listdir(BUILT)
                  if f.startswith("apoli-forge-") and f.endswith(".jar")
                  and not f.endswith("-all.jar")) if os.path.isdir(BUILT) else []
    if not hits:
        raise SystemExit("!! 建てた apoli が無い。⚠ `./gradlew :apoli:build` を回す。")
    return os.path.join(BUILT, hits[-1])


def run(jar=None, detail=False):
    want = scan_sources()
    n_need = sum(len(v) for v in want.values())
    print("== ソースが要求する参照 ==")
    print("   MixinExtras を使う mixin: %d クラス ／ 参照 %d 件" % (len(want), n_need))
    if detail:
        for cls, need in sorted(want.items()):
            print("   %s（%d 件）" % (cls, len(need)))
    jar = jar or default_jar()
    name, miss = missing(jar, want)
    print()
    print("== 見た refmap ==")
    print("   %s" % name)
    print()
    if miss:
        print("== ⚠⚠ 欠け %d 件 ==" % len(miss))
        last = None
        for cls, ref, where in miss:
            if cls != last:
                print("   %s" % cls)
                last = cls
            print("      !! %-64s （%s に無い）" % (ref[:64], where))
        print()
        print("⚠ **`mixinextras-common` が `annotationProcessor` に載っているか見る**"
              "（`build.gradle` の `project(\":apoli\")`）。")
        print("⚠ Mixin 0.8.5 の注釈処理は `@WrapOperation` を知らないので、"
              "載せないと refmap に書かれない。")
        return 1
    print("OK 欠けは無い（%d 件すべて refmap に在る）" % n_need)
    return 0


def self_test():
    """⚠ 陽性＝建てた jar（欠けが在るはず）／陰性＝配っている jar（欠け 0）。"""
    print("== 自己試験 ==")
    ng = 0
    want = scan_sources()
    if not want:
        print("  NG ソースから1件も採れていない（走査が壊れている）")
        return 1
    print("  ok ソースから %d クラス・%d 件を採った"
          % (len(want), sum(len(v) for v in want.values())))

    # ⚠ 陰性: 配っている jar は欠け 0（**あちらは正しく作られた refmap**）
    _n, miss_rel = missing(RELEASED, want)
    if miss_rel:
        print("  NG 陰性 配っている jar に欠けが %d 件（対照が壊れている）" % len(miss_rel))
        for c, r, w in miss_rel[:5]:
            print("       %s %s（%s）" % (c, r[:50], w))
        ng += 1
    else:
        print("  ok 陰性 配っている jar は欠け 0 件")

    # ⚠ 陽性: 建てた jar（直す前なら欠けが在る／直した後は 0）
    try:
        jb = default_jar()
    except SystemExit as e:
        print("  – 陽性 建てた jar が無いので試験しない（%s）" % e)
        return 1 if ng else 0
    _n2, miss_built = missing(jb, want)
    print("  ⚠ 建てた jar の欠け: %d 件" % len(miss_built))
    if miss_built:
        print("     → ⚠ **直す前の状態。** `annotationProcessor` を足して建て直すと 0 になるはず")
    else:
        print("     → ok 直っている")
    print("判定: NG %d 件" % ng)
    return 1 if ng else 0


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--jar")
    a.add_argument("--detail", action="store_true")
    a.add_argument("--self-test", action="store_true")
    ns = a.parse_args(argv)
    return self_test() if ns.self_test else run(jar=ns.jar, detail=ns.detail)


if __name__ == "__main__":
    sys.exit(main())
