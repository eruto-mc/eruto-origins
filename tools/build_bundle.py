# -*- coding: utf-8 -*-
"""Origins 一族の jar を**全部1つに混ぜて** `eruto-origins` の jar を作る。

  py -3.12 tools/build_bundle.py            … 何が起きるかだけ出す（作らない）
  py -3.12 tools/build_bundle.py --write    … jar を作る
  py -3.12 tools/build_bundle.py --self-test

## ⚠ なぜ入れ子にせず混ぜるか（2026-08-30・あなたの判断）

> 「jar 自体を混ぜる方が、結果として運用時に効率的になる」

⚠ **入れ子の中に隠れる物が無くなる**ので、壊れたときに1か所を見れば全部見える。
⚠ **版の折り合いが見えない所で起きなくなる**（下の「同じ土台が複数の版」を参照）。

⚠⚠ **もう1つ、設計書が最初から目的に挙げていたもの**:
同じ `data/` のパスが2つ在るとき、⚠ **いまは `loading_priority` と読み込み順で黙って勝敗が決まる**。
⚠ **混ぜると、決めない限り jar が作れない。**

## 入れる物（⚠ 版番号は書かない。名前の頭で引く）

上の 7 本と、その中に入れ子で入っている土台を**全部1段に引き上げる**。

## ⚠ 混ぜ方（1つしか置けない物）

| 物 | どうするか |
| - | - |
| `META-INF/mods.toml` | ⚠ `[[mods]]` と `[[dependencies.*]]` を**全部並べる**（実例: `embeddium` が `embeddium`＋`rubidium`、`letsdo-API` が `doapi`＋`terraform`） |
| `META-INF/MANIFEST.MF` | ⚠ **`MixinConfigs` に全部の設定を並べる**（落とすとログに1行も出ずに死ぬ） |
| `META-INF/accesstransformer.cfg` | 連結（どこから来たかの印を付ける） |
| `META-INF/coremods.json` | 対応表を合併。⚠ **鍵がぶつかったら落ちる** |
| `pack.mcmeta` | ⚠ `pack_format` が最大のものを1つ |
| `META-INF/jarjar/**` | ⚠ **入れない**（1段に引き上げたので） |

## ⚠⚠ 静かに間違えない作り

- ⚠ **同じ土台が複数の版で入っている**ときは、**高いほうだけ**を採る
  （⚠ **いま Forge がやっている折り合いと同じ規則**）。⚠ 採った版は必ず印字する
- ⚠ **決めていないぶつかりが1件でも在れば落ちる。** 許すものは下の表に**理由つき**で書く
- ⚠ MOR から抜く 8 個は `build_mor_patch.py` の `DROP` を読む（⚠ **写さない**）
"""
import argparse
import ast
import collections
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
MC = r"c:\@projects\minecraft-club"
MODS = os.path.join(MC, "worlds", "world-3", "dev", "instance", "mods")
MOR_PATCH = os.path.join(MC, "worlds", "world-3", "dev", "work", "mor_patch",
                         "build_mor_patch.py")
OUT_DIR = os.path.join(REPO, "build", "bundle")

# ⚠ 版番号を書かない（`check_power_refs.py` が版直書きで静かに落ちた・rule-misses 308）
TOP = [
    "origins-forge-",
    "origins-classes-forge-",
    "Medieval Origins Revival-",
    "solapplepie_origins_fix-",
    "origins_umbrellas-",
    "shifting_origins-",
    "orb_layer_variants-",
]

# ⚠⚠ **決めたぶつかり**。ここに無いぶつかりが出たら落ちる。
#    値は「どの入り口の物を採るか」の目印（jar の名前の頭）と理由。
DECIDED = {
    "data/origins/origin_layers/origin.json": (
        "origins-forge",
        "当部の `origins_setup` が `replace: true` で層を丸ごと置き換えるので、"
        "どちらを採っても画面には出ない。⚠ 上流の物を残す（段4で当部の層を jar へ移す）"),
    "data/origins/powers/light_armor.json": (
        "origins-forge",
        "⚠ 当部の写しは**上流と中身が同じ**と機械で確かめた（`show_collision.py`）。"
        "写しを消して上流の定義をそのまま効かせる"),
    "data/origins/powers/claustrophobia.json": (
        "origins-forge",
        "同上（上流と中身が同じ）"),
    "data/origins-classes/powers/explorer_kit.json": (
        "shifting_origins",
        "⚠ ここだけ**本物の上書き**（同じ中身の組が無い）。当部の物を採る"),
    "pack.png": (
        "origins-classes-forge",
        "⚠ 中身は**設定画面に出す絵**だけ（`mods.toml` の `logoFile`）。"
        "⚠ 遊びには1ミリも効かないので、Origins の物を1つ採る"),
}

MANIFEST_KEEP = ("Manifest-Version",)


def mor_drop():
    """MOR から抜く分を `build_mor_patch.py` から読む。⚠ **写さない。**"""
    with io.open(MOR_PATCH, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "DROP":
                    names = [ast.literal_eval(e) for e in node.value.elts]
                    return {"data/medievalorigins/powers/%s.json" % n for n in names}
    raise SystemExit("!! `DROP` を %s から読めない。⚠ 名前が変わったなら、ここも直す。" % MOR_PATCH)


def resolve(stem):
    hits = sorted(f for f in os.listdir(MODS)
                  if f.startswith(stem) and f.endswith(".jar"))
    if len(hits) != 1:
        raise SystemExit("!! `%s` で始まる jar が %d 本（1本であるべき）: %s"
                         % (stem, len(hits), ", ".join(hits) or "無し"))
    return os.path.join(MODS, hits[0])


def artifact_of(jar_name):
    """`mixinextras-forge-0.4.1.jar` → (`mixinextras-forge`, (0,4,1))"""
    base = jar_name[:-len(".jar")]
    m = re.match(r"^(.*?)-([0-9].*)$", base)
    if not m:
        return base, ()
    name, ver = m.group(1), m.group(2)
    return name, tuple(int(x) for x in re.findall(r"\d+", ver))


def collect(path, label, sink):
    """jar を開いて (入り口 → 中身) を集める。

    ⚠ **入れ子は辿らない。** どの版を採るかは `gather()` が**全部見つけてから**決める
    （⚠ ここで辿ると、段の深さの違いで版が競合しなくなる）。
    """
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith("/") or n.startswith("META-INF/jarjar/"):
                continue
            sink["entries"].setdefault(n, []).append((label, z.read(n)))


def gather():
    """全部の入り口を1段に引き上げて集める。返り値は sink と、採った土台の一覧。

    ⚠⚠ **版の選び方は「全部見つけてから、名前ごとに1つ」。**
    ⚠ 2026-08-30 に「見つけた順に、その回の中だけで比べる」書き方をしていて、
    ⚠⚠ **`mixinextras` の 0.2.1（Apugli の中の中）と 0.4.1（MOR の中）が
    別の回に居たので競合せず、2つの版が両方入っていた。**
    ⚠ 段の深さが違うだけで競合しないのは、⚠ **Forge の折り合いとも違う。**
    """
    # 第1段: 入れ子の jar を**全部**見つける（中身はまだ集めない）
    found = collections.defaultdict(list)      # 名前 → [(jar名, bytes, 出どころ)]

    def walk(blob, label):
        with zipfile.ZipFile(blob) as z:
            for n in z.namelist():
                if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                    inner = os.path.basename(n)
                    raw = z.read(n)
                    found[artifact_of(inner)[0]].append((inner, raw, label))
                    walk(io.BytesIO(raw), inner)

    for stem in TOP:
        p = resolve(stem)
        with open(p, "rb") as fh:
            walk(io.BytesIO(fh.read()), os.path.basename(p))

    # 第2段: 名前ごとに**版が最大の1つ**だけ採る
    chosen, dropped = [], []
    winners = []
    for art, items in sorted(found.items()):
        best = max(items, key=lambda it: artifact_of(it[0])[1])
        for it in items:
            if it[0] != best[0]:
                dropped.append((it[0], it[2]))
        chosen.append((best[0], best[2]))
        winners.append(best)

    # 第3段: 上の 7 本と、勝った土台だけから中身を集める
    sink = {"entries": {}, "nested": {}}
    for stem in TOP:
        p = resolve(stem)
        collect(p, os.path.basename(p), sink)
    for name, raw, _src in winners:
        collect(io.BytesIO(raw), name, sink)
    return sink, chosen, sorted(set(dropped))


# ⚠⚠ **合わせた jar は `license=` を1つしか書けない。**
#    ⚠ そのまま最初の1本（MIT）を採ると、⚠ **LGPL-3.0 の umbrellas を MIT と名乗ることになる。**
#    ⚠ 知らない免許が混ざったら**落とす**（黙って MIT にしない）。
KNOWN_LICENSES = {"MIT", "CC0 1.0 Universal", "LGPL-3.0-only"}


def licenses_of(texts):
    """(modId, 免許, 出どころ) を集める。⚠ 知らない免許が在れば落ちる。"""
    out = []
    for label, t in texts:
        m = re.search(r'^\s*license\s*=\s*["\']([^"\']+)', t, re.M)
        lic = m.group(1).strip() if m else "（宣言なし）"
        ids, inmods = [], False
        for line in t.splitlines():
            s = re.sub(r"#.*$", "", line).strip()
            if s.startswith("[["):
                inmods = (s == "[[mods]]"); continue
            if s.startswith("["):
                inmods = False; continue
            if inmods:
                mm = re.match(r'modId\s*=\s*"([^"]+)"', s)
                if mm:
                    ids.append(mm.group(1))
        for i in ids:
            out.append((i, lic, label))
        if lic not in KNOWN_LICENSES:
            raise SystemExit(
                "!! 知らない免許が混ざった: %s（%s）\n"
                "⚠ **黙って他の免許で名乗らない。** 中身を読んで `KNOWN_LICENSES` へ足す。"
                % (lic, label))
    return out


def merge_mods_toml(texts):
    """`[[mods]]` と `[[dependencies.*]]` を全部並べる。⚠ 前置きは最初の1本から採る。

    ⚠⚠ **`license=` だけは書き換える**（合わせた中身を全部並べる）。
    """
    lics = licenses_of(texts)
    combined = " AND ".join(sorted({l for _i, l, _s in lics}))
    head, body = [], []
    for i, (label, t) in enumerate(texts):
        lines = t.replace("\r\n", "\n").split("\n")
        start = next((k for k, s in enumerate(lines)
                      if re.sub(r"#.*$", "", s).strip().startswith("[[")), len(lines))
        if i == 0:
            head = [re.sub(r'^\s*license\s*=.*$', 'license="%s"' % combined, s)
                    for s in lines[:start]]
        body.append("# ---- %s ----" % label)
        body.extend(lines[start:])
    return "\n".join(head + body) + "\n", lics, combined


def merge_coremods(items):
    out = {}
    for label, raw in items:
        d = json.loads(raw.decode("utf-8"))
        for k, v in d.items():
            if k in out and out[k][0] != v:
                raise SystemExit("!! coremods の鍵がぶつかった: %s（%s と %s）"
                                 % (k, out[k][1], label))
            out[k] = (v, label)
    return json.dumps({k: v for k, (v, _l) in out.items()}, indent=2, ensure_ascii=False)


def pick_pack(items):
    best, bestfmt = None, -1
    for label, raw in items:
        try:
            fmt = json.loads(raw.decode("utf-8"))["pack"]["pack_format"]
        except Exception:
            continue
        if fmt > bestfmt:
            best, bestfmt = raw, fmt
    return best, bestfmt


def run(write=False):
    drop = mor_drop()
    sink, chosen, dropped = gather()
    entries = sink["entries"]

    print("== 入れた jar ==")
    for stem in TOP:
        print("   %s" % os.path.basename(resolve(stem)))
    print("== 入れ子から引き上げた土台（⚠ 高いほうを採る）==")
    for name, src in sorted(chosen):
        print("   %-46s ← %s" % (name, src))
    if dropped:
        print("== ⚠ 版が低いので採らなかったもの（必ず出す）==")
        for name, src in sorted(dropped):
            print("   %-46s ← %s" % (name, src))

    special = ("META-INF/mods.toml", "META-INF/MANIFEST.MF",
               "META-INF/accesstransformer.cfg", "META-INF/coremods.json",
               "pack.mcmeta")
    cfgs = sorted({n for n in entries if n.endswith(".mixins.json") and "/" not in n})

    bad = []
    for n, owners in sorted(entries.items()):
        if n in special or len(owners) == 1:
            continue
        blobs = {b for _l, b in owners}
        if len(blobs) == 1:
            continue                       # ⚠ 中身が同じなら問題にしない
        if n in DECIDED:
            continue
        bad.append((n, [l for l, _b in owners]))

    print()
    print("== 数 ==")
    print("   入り口 %d ／ mixin の設定 %d 本 ／ ⚠ 決めていないぶつかり %d 件"
          % (len(entries), len(cfgs), len(bad)))
    print("   ⚠ MOR から抜く: %d 件" % len(drop))
    print("== 決めたぶつかり（%d 件・理由つき）==" % len(DECIDED))
    for n, (who, why) in sorted(DECIDED.items()):
        here = n in entries
        print("   %s %-52s → %s" % ("  " if here else "!!", n, who))
        print("        %s" % why)
        if not here:
            bad.append((n, ["⚠ もう存在しない（決定が古い）"]))
    if bad:
        print()
        print("== ⚠⚠ 決めていないぶつかり ==")
        for n, owners in bad:
            print("   !! %-58s %s" % (n, ", ".join(owners)))
        print("⚠ **どれを採るか決めて `DECIDED` に理由つきで書くまで作らない。**")
        return 1

    if not write:
        print()
        print("⚠ `--write` を付けると作る（いまは作っていない）。")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "eruto-origins-0.1.0.jar")
    at = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, owners in sorted(entries.items()):
            if n in drop or n.startswith("META-INF/jarjar/"):
                continue
            if n == "META-INF/MANIFEST.MF":
                continue
            if n == "META-INF/mods.toml":
                toml, lics, combined = merge_mods_toml(
                    [(l, b.decode("utf-8", "replace")) for l, b in owners])
                z.writestr(n, toml)
                print("   免許: %s" % combined)
                # ⚠⚠ **どの modId がどの免許かを jar の中に残す**（段3の「LGPL の表示」）。
                lines = ["# この jar に入っている物の免許", "",
                         "⚠ **1つの jar に複数の MOD を混ぜてある。**",
                         "⚠ `mods.toml` の `license` はそれらを並べたもの。", "",
                         "| modId | 免許 | 出どころ |", "| - | - | - |"]
                for i, l, s in sorted(lics):
                    lines.append("| `%s` | %s | %s |" % (i, l, s))
                lines += ["", "⚠ 免許の全文は、それを持っていた MOD の物を",
                          "この jar の中にそのまま入れてある（`LICENSE*`）。"]
                z.writestr("LICENSES.md", "\n".join(lines) + "\n")
                continue
            if n == "META-INF/accesstransformer.cfg":
                for l, b in owners:
                    at.append("# ---- %s ----\n%s" % (l, b.decode("utf-8", "replace")))
                continue
            if n == "META-INF/coremods.json":
                z.writestr(n, merge_coremods(owners))
                continue
            if n == "pack.mcmeta":
                raw, fmt = pick_pack(owners)
                print("   pack.mcmeta: pack_format %d を採った" % fmt)
                z.writestr(n, raw)
                continue
            pick = DECIDED[n][0] if n in DECIDED else None
            blob = next((b for l, b in owners if pick and l.startswith(pick)),
                        owners[0][1])
            z.writestr(n, blob)
        z.writestr("META-INF/accesstransformer.cfg", "\n".join(at))
        z.writestr("META-INF/MANIFEST.MF",
                   "Manifest-Version: 1.0\r\n"
                   "MixinConfigs: %s\r\n" % ",".join(cfgs))
    print()
    print("作った: %s（%d バイト）" % (out, os.path.getsize(out)))
    return 0


def self_test():
    print("== 自己試験 ==")
    ng = 0
    d = mor_drop()
    if len(d) == 8:
        print("  ok DROP を 8 件読めた")
    else:
        print("  NG DROP が %d 件" % len(d)); ng += 1

    # ⚠ 陽性: 版の比べ方が壊れていないこと
    got = artifact_of("mixinextras-forge-0.4.1.jar")
    want = ("mixinextras-forge", (0, 4, 1))
    if got == want:
        print("  ok 陽性 版の読み取り %s" % (got,))
    else:
        print("  NG 陽性 版の読み取りが %s（%s のはず）" % (got, want)); ng += 1
    a = artifact_of("mixinextras-forge-0.2.0-beta.8.jar")[1]
    b = artifact_of("mixinextras-forge-0.2.1.jar")[1]
    if b > a:
        print("  ok 陽性 0.2.1 が 0.2.0-beta.8 より高い")
    else:
        print("  NG 陽性 版の大小が逆（%s vs %s）" % (a, b)); ng += 1

    # ⚠ 陽性: 存在しない目印で落ちること
    try:
        resolve("zzz-no-such-")
        print("  NG 陽性 存在しない目印で落ちなかった"); ng += 1
    except SystemExit:
        print("  ok 陽性 存在しない目印は落ちる")

    # ⚠ 陰性: 決めた表の宛先が、実際にその入り口を持っていること
    sink, _c, _d = gather()
    for n, (who, _why) in sorted(DECIDED.items()):
        owners = [l for l, _b in sink["entries"].get(n, [])]
        if any(l.startswith(who) for l in owners):
            print("  ok 陰性 %s の宛先 %s が居る" % (n.split("/")[-1], who))
        else:
            print("  NG 陰性 %s の宛先 %s が居ない（居るのは %s）"
                  % (n, who, ", ".join(owners) or "誰も"))
            ng += 1
    print("判定: NG %d 件" % ng)
    return 1 if ng else 0


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--write", action="store_true")
    a.add_argument("--self-test", action="store_true")
    ns = a.parse_args(argv)
    return self_test() if ns.self_test else run(write=ns.write)


if __name__ == "__main__":
    sys.exit(main())
