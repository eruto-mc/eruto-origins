# -*- coding: utf-8 -*-
"""⚠⚠ **ソースの注釈が要求する参照が、refmap に載っているか**を突き合わせる。

  py -3.12 tools/check_refmap_coverage.py                 … 混ぜた jar を見る（4 つの置き場ぶん）
  py -3.12 tools/check_refmap_coverage.py --jar <jar>     … 好きな jar を見る
  py -3.12 tools/check_refmap_coverage.py --module origins … 1 つの置き場だけ見る
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

## ⚠ 見る範囲（2026-09-25 に apoli だけから 4 つへ広げた）

| 置き場 | ソース | refmap |
| - | - | - |
| apoli | `apoli/src/main/java` | `apoli.refmap.json` |
| origins | `origins/src/main/java`（当部の `shiftingorigins` も） | `origins.refmap.json` |
| medieval | `medieval/common`・`medieval/forge`（⚠ `fabric` は建てないので見ない） | `medievalorigins.refmap.json` |
| umbrellas | `umbrellas/src/main/java` | `originsumbrellas.refmap.json` |

⚠ それまでは apoli しか見ておらず、⚠ **当部の mixin（`shiftingorigins`）の `@WrapOperation` は1件も確かめていなかった**。
⚠ 相手は既定で**混ぜた jar**（`build/bundle` の最新。無ければ `instance/mods` の配っている物）——
README の手順どおり `build_bundle.py --write` の後に回す。4 つの refmap はどれもその中に在る。

## ⚠ 見るもの

ソースの MixinExtras の注入注釈から、⚠ **refmap に載っているべき参照**を集める:

  * `method = "..."`        … 当てる先のメソッド（⚠ **記述子ごとが鍵**）
  * `@At(target = "...")`   … 注入点の当て先

⚠ それが refmap の `mappings` と `data.searge` の両方に在るかを見る
（⚠ **Forge の実行時が見るのは `data.searge`**）。

## ⚠ 取りこぼしやすい所（`projects-70` が試作で2回踏んだ）

  1. ⚠ `method = "render(Lnet/…;…)V"` は**記述子ごと**が鍵。`(` で切ると当たらない
  2. ⚠ 他所の MOD のクラスへ当てる mixin（`@Mixin(targets = "com.unascribed.ears.…")` や
     `@Mixin(value = …, remap = false)`）は難読化されない。その `method=` は refmap に無いのが正しい
  3. ⚠ 注釈の引数は**括弧を数えて**採る。`.*?` は `(I)Z` の括弧で切れる
  4. ⚠⚠ **`@At` の当て先が refmap に要るかは、当て先の「クラス」で決める**（2026-09-25）。
     それまでは文字列に `net/minecraft` が含まれるかで見ていたので、他所の MOD のメソッドでも
     引数に Minecraft の型が在るだけで「要る」と誤判定した
     （例: 当部の `LunchboxDietMixin` の `…/integration/Origins;hasRestrictedDiet(Lnet/minecraft/…/Player;)Z`）
  5. ⚠⚠ **`"…" + "…"` と `+` でつないだ文字列は1つとして読む**（2026-09-25）。
     最初の1片だけを採ると、当て先を3行に分けて書いた `CraftingResultMixin` を「クラスの名前だけ」と読み、
     ⚠ **在る参照を「欠け」と誤判定する**（広げた日に実際にそう出た）
"""
import argparse
import copy
import glob
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
BUNDLE = os.path.join(REPO, "build", "bundle")
# ⚠ 当部の手元のフォルダは `build_bundle.py` と同じ求め方（作者の手元の置き方が前提・
#   違うなら環境変数 `ERUTO_CLUB_DIR` で読み替える）。⚠ 公開の置き場なので手元の絶対パスを書かない。
MODS = os.path.join(os.environ.get("ERUTO_CLUB_DIR") or os.path.abspath(os.path.join(REPO, "..", "..")),
                    "worlds", "world-3", "dev", "instance", "mods")

# (名前, ソースの根, refmap の名前)。⚠ 置き場を足したらここに1行足す。
MODULES = [
    ("apoli", ["apoli/src/main/java"], "apoli.refmap.json"),
    ("origins", ["origins/src/main/java"], "origins.refmap.json"),
    ("medieval", ["medieval/common/src/main/java", "medieval/forge/src/main/java"],
     "medievalorigins.refmap.json"),
    ("umbrellas", ["umbrellas/src/main/java"], "originsumbrellas.refmap.json"),
]

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


LITERAL = re.compile(r'\s*"((?:[^"\\]|\\.)*)"')


def concat_at(s, i):
    """`"a" + "b" + "c"` を1つの文字列として採る。返り値: (文字列, 次の位置) ／ 無ければ (None, i)。

    ⚠⚠ **`+` でつないだ文字列を1つとして読む**（2026-09-25）。それまでは最初の1片だけを採っており、
    当て先を3行に分けて書いた `CraftingResultMixin` を「クラスの名前だけ」と読んで、欠けと誤判定した。
    """
    m = LITERAL.match(s, i)
    if not m:
        return None, i
    parts, j = [m.group(1)], m.end()
    while True:
        k = j
        while k < len(s) and s[k].isspace():
            k += 1
        if k < len(s) and s[k] == "+":
            m2 = LITERAL.match(s, k + 1)
            if m2:
                parts.append(m2.group(1))
                j = m2.end()
                continue
        return "".join(parts), j


def strings_for(key, block):
    """`key = "..."` と `key = {"...","..."}` の両方から文字列を採る（`+` でつないだ物は1つにする）。"""
    out = []
    m = re.search(r'\b%s\s*=\s*' % key, block)
    if not m:
        return out
    i = m.end()
    while i < len(block) and block[i].isspace():
        i += 1
    if i < len(block) and block[i] == "{":
        i += 1
        while i < len(block):
            got, i = concat_at(block, i)
            if got is None:
                break
            out.append(got)
            while i < len(block) and block[i].isspace():
                i += 1
            if i < len(block) and block[i] == ",":
                i += 1
                continue
            break
    else:
        got, _i = concat_at(block, i)
        if got is not None:
            out.append(got)
    return out


def owner_is_minecraft(target):
    """⚠ `@At` の当て先が refmap に要るか＝**当て先のクラスが Minecraft か**（2026-09-25）。

    `Lpkg/Cls;name(desc)` の形なら `;` の前のクラスで決める（引数の型では決めない）。
    それ以外の形（`NEW` の当て先など）は、これまでどおり文字列に `net/minecraft` が在るかで見る。
    """
    if target.startswith("L") and ";" in target:
        return target[1:target.index(";")].startswith("net/minecraft/")
    return "net/minecraft" in target


def scan_sources(roots):
    """ソースから (mixin クラスの内部名 → 要求する参照の集合) を作る。"""
    want = {}
    for root in roots:
        src = os.path.join(REPO, root)
        for dp, _dn, fs in os.walk(src):
            for f in fs:
                if not f.endswith(".java"):
                    continue
                p = os.path.join(dp, f)
                with io.open(p, encoding="utf-8", errors="replace") as fh:
                    t = fh.read()
                if not any(("@" + a) in t for a in MIXINEXTRAS):
                    continue
                rel = os.path.relpath(p, src).replace(os.sep, "/")[:-len(".java")]
                # ⚠ 他所の MOD のクラスへ当てる mixin＝難読化されない（`method=` は refmap に無いのが正しい）
                mx = re.search(r"@Mixin\s*\(", t)
                foreign = False
                if mx:
                    a = args_of(t, mx.start())
                    tg = strings_for("targets", a)
                    foreign = (bool(tg) and not any(x.startswith("net.minecraft") for x in tg)) \
                        or bool(re.search(r"\bremap\s*=\s*false", a))
                need = set()
                for ann in MIXINEXTRAS:
                    for m in re.finditer(r"@%s\s*\(" % ann, t):
                        block = args_of(t, m.start())
                        if not foreign:
                            # ⚠ **記述子ごとが鍵**（`(` で切らない）
                            need |= set(strings_for("method", block))
                        for at in re.finditer(r"@At\s*\(", block):
                            ab = args_of(block, at.start())
                            if re.search(r"\bremap\s*=\s*false", ab):
                                continue
                            for tgt in strings_for("target", ab):
                                if owner_is_minecraft(tgt):
                                    need.add(tgt)
                if need:
                    want[rel] = need
    return want


def refmap_in(jar, name):
    """jar（入れ子も辿る）から、その名前の refmap を採る。返り値: (見出し, 中身) ／ 無ければ None。"""
    def dig(z, label):
        for n in z.namelist():
            if os.path.basename(n) == name:
                return "%s ▸ %s" % (label, n), json.loads(z.read(n).decode("utf-8-sig"))
        for n in z.namelist():
            if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                with zipfile.ZipFile(io.BytesIO(z.read(n))) as iz:
                    got = dig(iz, "%s ▸ %s" % (label, os.path.basename(n)))
                    if got:
                        return got
        return None
    with zipfile.ZipFile(jar) as z:
        return dig(z, os.path.basename(jar))


def missing_in(d, want):
    """refmap（中身）に載っていない参照を数える。返り値: [(クラス, 参照, どちらの表に無いか)]"""
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
    return out


def newest(pattern):
    hits = sorted(glob.glob(pattern), key=os.path.getmtime)
    return hits[-1] if hits else None


def default_jar():
    """⚠ 混ぜた jar。`build/bundle` の最新 → 無ければ `instance/mods` の配っている物。"""
    jar = newest(os.path.join(BUNDLE, "eruto-origins-*.jar")) \
        or newest(os.path.join(MODS, "eruto-origins-*.jar"))
    if not jar:
        raise SystemExit("!! 混ぜた jar が無い。⚠ `py -3.12 tools/build_bundle.py --write` を回す。")
    return jar


def deployed_jar():
    return newest(os.path.join(MODS, "eruto-origins-*.jar"))


def run(jar=None, only=None, detail=False):
    jar = jar or default_jar()
    print("== 見る jar: %s" % jar)
    total_need = total_miss = 0
    bad = False
    for name, roots, refname in MODULES:
        if only and name != only:
            continue
        want = scan_sources(roots)
        n_need = sum(len(v) for v in want.values())
        total_need += n_need
        print()
        print("== %s: MixinExtras を使う mixin %d クラス ／ 参照 %d 件" % (name, len(want), n_need))
        if detail:
            for cls, need in sorted(want.items()):
                print("   %s（%d 件）" % (cls, len(need)))
        if not want:
            continue
        got = refmap_in(jar, refname)
        if not got:
            print("   !! jar に %s が無い" % refname)
            bad = True
            continue
        label, d = got
        print("   見た refmap: %s" % label)
        miss = missing_in(d, want)
        total_miss += len(miss)
        if miss:
            bad = True
            print("   ⚠⚠ 欠け %d 件" % len(miss))
            last = None
            for cls, ref, where in miss:
                if cls != last:
                    print("   %s" % cls)
                    last = cls
                print("      !! %-64s （%s に無い）" % (ref[:64], where))
        else:
            print("   OK 欠けは無い")
    print()
    if bad:
        print("⚠ **その置き場の `build.gradle` で、`mixinextras-common` が `annotationProcessor` に"
              "載っているか見る。** Mixin 0.8.5 の注釈処理は `@WrapOperation` を知らないので、"
              "載せないと refmap に書かれない。⚠ 他所の MOD へ当てる mixin で Minecraft の当て先を使うなら "
              "`@At(… remap = true)` が要る。")
        return 1
    print("OK 欠けは無い（%d 件すべて refmap に在る）" % total_need)
    return 0


def self_test():
    """⚠ 陰性＝配っている jar（欠け 0）／陽性＝refmap から1件消した写し（欠け 1）／判定の対照。"""
    print("== 自己試験 ==")
    ng = 0
    wants = {name: scan_sources(roots) for name, roots, _r in MODULES}
    for name in ("apoli", "origins"):
        if not wants[name]:
            print("  NG %s のソースから1件も採れていない（走査が壊れている）" % name)
            ng += 1
        else:
            print("  ok %s のソースから %d クラス・%d 件を採った"
                  % (name, len(wants[name]), sum(len(v) for v in wants[name].values())))

    # ⚠ 判定の対照: 他所の MOD のメソッドは、引数に Minecraft の型が在っても要らない
    lb = wants["origins"].get("net/erutobusiness/shiftingorigins/mixin/LunchboxDietMixin")
    if lb is None:
        print("  – 判定 LunchboxDietMixin が無いので試験しない")
    else:
        edible = any("ItemStack;isEdible" in r for r in lb)
        foreign = any("hasRestrictedDiet" in r for r in lb)
        if edible and not foreign:
            print("  ok 判定 Minecraft の当て先（isEdible）は要る・他所の当て先（hasRestrictedDiet）は要らない")
        else:
            print("  NG 判定 isEdible=%s（要る）／ hasRestrictedDiet=%s（要らない）" % (edible, foreign))
            ng += 1

    # ⚠ 読み方の対照: `+` でつないだ当て先を1つとして読めているか
    cr = wants["origins"].get("net/erutobusiness/shiftingorigins/mixin/CraftingResultMixin")
    if cr is None:
        print("  – 読み方 CraftingResultMixin が無いので試験しない")
    elif any(r.endswith(";assemble(Lnet/minecraft/world/Container;Lnet/minecraft/core/RegistryAccess;)"
                        "Lnet/minecraft/world/item/ItemStack;") for r in cr) \
            and "Lnet/minecraft/world/item/crafting/CraftingRecipe;" not in cr:
        print("  ok 読み方 `+` でつないだ当て先を1つとして読んだ（CraftingResultMixin）")
    else:
        print("  NG 読み方 `+` でつないだ当て先を切れ端で読んでいる: %s" % sorted(cr))
        ng += 1

    # ⚠ 陰性: 配っている jar は欠け 0（本番で mixin が当たっている物）
    dj = deployed_jar()
    if not dj:
        print("  NG 陰性 配っている jar が無い（%s）" % MODS)
        return 1
    first = None
    for name, _roots, refname in MODULES:
        want = wants[name]
        if not want:
            continue
        got = refmap_in(dj, refname)
        if not got:
            print("  NG 陰性 %s に %s が無い" % (os.path.basename(dj), refname))
            ng += 1
            continue
        miss = missing_in(got[1], want)
        if miss:
            print("  NG 陰性 配っている jar の %s に欠けが %d 件（対照が壊れているか、ソースが先へ進んでいる）"
                  % (refname, len(miss)))
            for c, r, w in miss[:5]:
                print("       %s %s（%s）" % (c, r[:50], w))
            ng += 1
        else:
            print("  ok 陰性 配っている jar の %s は欠け 0 件" % refname)
            if first is None:
                first = (name, got[1], want)

    # ⚠ 陽性: refmap から1件消した写しを作り、⚠ **その1件を拾えるか**
    if first:
        name, d, want = first
        cls, need = sorted(want.items())[0]
        ref = sorted(need)[0]
        broken = copy.deepcopy(d)
        broken.get("mappings", {}).get(cls, {}).pop(ref, None)
        broken.get("data", {}).get("searge", {}).get(cls, {}).pop(ref, None)
        miss = missing_in(broken, want)
        if [(c, r) for c, r, _w in miss] == [(cls, ref)]:
            print("  ok 陽性 %s の refmap から1件消した写しで、その1件だけを拾った（%s）" % (name, ref[:50]))
        else:
            print("  NG 陽性 1件消したのに %d 件拾った" % len(miss))
            ng += 1
    print("判定: NG %d 件" % ng)
    return 1 if ng else 0


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--jar")
    a.add_argument("--module", choices=[m[0] for m in MODULES])
    a.add_argument("--detail", action="store_true")
    a.add_argument("--self-test", action="store_true")
    ns = a.parse_args(argv)
    return self_test() if ns.self_test else run(jar=ns.jar, only=ns.module, detail=ns.detail)


if __name__ == "__main__":
    sys.exit(main())
