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

上の 7 本を**1つに混ぜる**。⚠ **その中の土台（calio・apoli・AEA・Apugli・mixinextras）は
入れ子のまま**入れる（版の重なりは Forge に任せる）。

## ⚠ 混ぜ方（1つしか置けない物）

| 物 | どうするか |
| - | - |
| `META-INF/mods.toml` | ⚠ `[[mods]]` と `[[dependencies.*]]` を**全部並べる**（実例: `embeddium` が `embeddium`＋`rubidium`、`letsdo-API` が `doapi`＋`terraform`）。⚠⚠ **`${file.jarVersion}` はここで実数へ埋める**（下記） |
| `META-INF/MANIFEST.MF` | ⚠ **`MixinConfigs` に全部の設定を並べる**（落とすとログに1行も出ずに死ぬ） |
| `META-INF/accesstransformer.cfg` | 連結（どこから来たかの印を付ける） |
| `META-INF/coremods.json` | 対応表を合併。⚠ **鍵がぶつかったら落ちる** |
| `pack.mcmeta` | ⚠ `pack_format` が最大のものを1つ |
| `META-INF/jarjar/**` | ⚠⚠ **土台は入れ子のまま入れる。溶かさない。**⚠ 2026-08-30 に溶かして遊び用サーバが起動できなかった（`mixinextras` を**他の MOD 30 本**が持っており、`Modules origins and mixinextras export package …` で落ちる）。⚠ **重なりを整理するのは JarJar の仕事** |

## ⚠⚠ 静かに間違えない作り

- ⚠ **同じ土台が複数の版で入っている**ときは、**高いほうだけ**を採る
  （⚠ **いま Forge がやっている折り合いと同じ規則**）。⚠ 採った版は必ず印字する
- ⚠ **決めていないぶつかりが1件でも在れば落ちる。** 許すものは下の表に**理由つき**で書く
- ⚠ MOR から抜く 8 個は `build_mor_patch.py` の `DROP` を読む（⚠ **写さない**）
- ⚠⚠ **`${file.jarVersion}` は混ぜる時点で実数へ埋める**（`substitute_jar_version`）。
  ⚠ Forge はこれを MANIFEST の `Implementation-Version` から解決するが、
  ⚠⚠ **混ぜた jar の MANIFEST は 1 つしか無い**ので、6 本ぶんの版を残せない。
  ⚠ 埋めずに作ると `originsumbrellas` と `shiftingorigins` が **`0.0NONE`** になり、
  ⚠⚠ **サーバは何事も無く動く**（2026-09-01 に実機で捕まえた）

## ⚠ 作った後に必ず回すもの

    py -3.12 tools/check_bundle_parity.py

⚠ **混ぜる前の 7 本と、混ぜた後の 1 本が同じことを名乗っているか**を突き合わせる。
⚠⚠ **この道具（作る側）は「起動しない」型しか見ていない。**
⚠ 「起動して、動いて、値だけが違う」型は、あちら（検査する側）でしか捕まらない。
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
    "origins_umbrellas-",
    "shifting_origins-",
    "orb_layer_variants-",
]

# ⚠⚠ **混ぜずに、入れ子のまま入れる MOD。**
#
# ⚠ 2026-08-30 に `solapplepie_origins_fix` を混ぜて、遊び用サーバが落ちた:
#
#     File eruto-origins-0.1.0.jar constructed 6 mods: [...],
#     but had 7 mods specified: [..., solapplepie_origins_fix]
#     The following classes are missing, but are reported in the mods.toml:
#       [solapplepie_origins_fix]
#
# ⚠ 原因は **`modLoader` が違う**こと——あちらは **`lowcodefml`**（Java のクラスを持たない形）で、
# ⚠⚠ **1つの `mods.toml` は `modLoader` を1つしか持てない。**
# ⚠ `javafml` の下に並べると、Forge は `@Mod` のクラスを探して見つからずに落ちる。
NEST_AS_IS = {
    "solapplepie_origins_fix-": {
        "group": "eruto-mc",       # ⚠ 当部が包み直したもの、という意味の名前
        "artifact": "solapplepie_origins_fix",
    },
}

# ⚠⚠ **決めたぶつかり**。ここに無いぶつかりが出たら落ちる。
#    値は「どの入り口の物を採るか」の目印（jar の名前の頭）と理由。
DECIDED = {
    "data/origins/origin_layers/origin.json": (
        "origins-forge",
        "当部の `origins_setup` が `replace: true` で層を丸ごと置き換えるので、"
        "どちらを採っても画面には出ない。⚠ 上流の物を残す（段4で当部の層を jar へ移す）"),
    # ⚠⚠ **2026-09-01 に理由文を書き直した。前の理由は誤りだった。**
    #
    # ⚠ 前は「当部の写しは**上流と中身が同じ**と機械で確かめた」と書いていたが、
    # ⚠⚠ **「当部の写し」が2つ在るのを1つと取り違えていた**（実物を開いて確認）:
    #
    #     origins-forge      loading_priority=0    hidden=false  compare_to=2    上流
    #     shifting_origins   loading_priority=100  hidden=true   compare_to=999  ⚠ **無効化した版**
    #     origins_setup      loading_priority=200  hidden=false  compare_to=2    上流と同じ内容
    #
    # ⚠ **バイト一致の組は無し。** 上流と同じなのは `origins_setup` のほうで、
    # ⚠ ここで消しているのは `shifting_origins`（無効化した版）。
    #
    # ⚠ 正しい理由は **2026-08-29 の決定**（設計書「重複5件の決着」）——
    # ⚠ **`light_armor` と `claustrophobia` は「有効」を正とし、jar 側の「（当部で無効化）」を消す。**
    #
    # ⚠ 挙動は変わらない: `origins_setup` の 200 が 0 も 100 も上回るので、
    # ⚠ いまも（0/100/200 のうち）200 が勝っており、100 を落としても 200 が勝つ。
    # ⚠⚠ **ただし段4で `origins_setup` を jar へ入れるときは、200 の側を残すこと**
    #    （1つの jar に2つ置けないので、0 の側を残すと無効化ではなく**上流の定義**に戻る）。
    "data/origins/powers/light_armor.json": (
        "origins-forge",
        "⚠ 2026-08-29 の決定で「有効」を正とした。⚠ 消しているのは "
        "`shifting_origins` の**無効化した版**（優先度100・`hidden`）。"
        "⚠ 実際に勝つのは `origins_setup` の優先度200"),
    "data/origins/powers/claustrophobia.json": (
        "origins-forge",
        "同上（⚠ `shifting_origins` の無効化した版を消す。優先度200 が勝つ）"),
    "data/origins-classes/powers/explorer_kit.json": (
        "shifting_origins",
        "⚠ ここだけ**本物の上書き**（同じ中身の組が無い）。当部の物を採る"),
    "pack.png": (
        "origins-classes-forge",
        "⚠ 中身は**設定画面に出す絵**だけ（`mods.toml` の `logoFile`）。"
        "⚠ 遊びには1ミリも効かないので、Origins の物を1つ採る"),
}

# ⚠ 各 jar が「自分のもの」として書いてよい `data/<名前空間>/`。
OWN_NS = {
    "origins-forge-": {"origins"},
    "origins-classes-forge-": {"origins-classes"},
    "Medieval Origins Revival-": {"medievalorigins"},
    "origins_umbrellas-": {"originsumbrellas"},
    "shifting_origins-": {"shiftingorigins"},
    "orb_layer_variants-": set(),
}

# ⚠⚠ **他人の名前空間へ書いてよいと決めた分**（ぶつかっていなくても要る）。
#
# ⚠ 2026-09-01 のあなたの指摘: 「origins でやってるのを classes で上書きして、
# ⚠ 独自でまた上書きして、が常態化したままだと統合の意味がない。
# ⚠ そういう各処理をわざわざ追っていく必要性を無くしてほしい」
#
# ⚠⚠ **`DECIDED` は「同じパスがぶつかったとき」しか鳴らない。**
# ⚠ 相手の名前空間へ**新しい名前で**置かれたら、⚠ **ぶつからないので黙って通る。**
# ⚠ それも「相手の領分に入っている」＝**追いかけが要る**状態なので、ここで鳴らす。
CROSS_NS_OK = {
    "data/forge/tags/damage_types/is_magic.json":
        "⚠ Forge の共有タグ。⚠ **タグは上書きではなく足し合わせ**なので、"
        "他の MOD の分を消さない（追いかけが要らない）",
}

MANIFEST_KEEP = ("Manifest-Version",)


def check_cross_namespace(entries):
    """⚠⚠ **相手の名前空間へ書いている data を全部出す**（ぶつかっていなくても）。

    返り値: [(パス, 書いた jar, 説明が在るか)]
    """
    out = []
    for n, owners in sorted(entries.items()):
        if not n.startswith("data/") or n.count("/") < 2:
            continue
        ns = n.split("/")[1]
        if ns == "minecraft":
            continue                     # ⚠ バニラの名前空間は誰でも足す（タグ・戦利品）
        for label, _blob in owners:
            own = next((v for k, v in OWN_NS.items() if label.startswith(k)), None)
            if own is None or ns in own:
                continue
            why = CROSS_NS_OK.get(n) or (DECIDED[n][1] if n in DECIDED else None)
            out.append((n, label, why))
    return out


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


DISABLED = os.path.join(os.path.dirname(MODS), "_disabled")


def resolve(stem):
    """元の jar を1本に決める。

    ⚠⚠ **退避先も見る。** ⚠ 2026-08-30 に、入れ替えた後は `instance/mods` に元の jar が
    無いので**作り直せなかった**（試験の途中で道具が使えなくなる）。
    ⚠ 退避先には**古い版も居る**ので、⚠ **版が最大の1本**を採り、そのことを印字する。
    """
    hits = sorted(f for f in os.listdir(MODS)
                  if f.startswith(stem) and f.endswith(".jar"))
    if len(hits) == 1:
        return os.path.join(MODS, hits[0])
    if len(hits) > 1:
        raise SystemExit("!! `%s` で始まる jar が mods に %d 本ある: %s"
                         % (stem, len(hits), ", ".join(hits)))
    back = sorted(f for f in os.listdir(DISABLED)
                  if f.startswith(stem) and f.endswith(".jar")) \
        if os.path.isdir(DISABLED) else []
    if not back:
        raise SystemExit("!! `%s` で始まる jar が mods にも退避先にも無い" % stem)
    best = max(back, key=lambda f: artifact_of(f)[1])
    print("   ⚠ %s は退避先から採った（%d 本のうち版が最大）" % (best, len(back)))
    return os.path.join(DISABLED, best)


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

    # 第3段: 上の 7 本の中身だけ集める。
    # ⚠⚠ **土台は溶かさない。入れ子のまま入れる。**
    #    ⚠ 2026-08-30 に溶かして遊び用サーバが**起動できなかった**:
    #      java.lang.module.ResolutionException:
    #        Modules origins and mixinextras export package
    #        com.llamalad7.mixinextras.platform.forge to module ...
    #    ⚠ `mixinextras` は**他の MOD 30 本が入れ子で持っている**。
    #    ⚠⚠ **重なりを整理するのは JarJar の仕事**で、そこを奪ってはいけない。
    sink = {"entries": {}, "nested": {}}
    for stem in TOP:
        p = resolve(stem)
        collect(p, os.path.basename(p), sink)
    return sink, chosen, sorted(set(dropped)), winners


def nest_as_is():
    """混ぜずに入れ子で入れる MOD を (jar名, 中身, identifier) で返す。"""
    out = []
    for stem, ident in sorted(NEST_AS_IS.items()):
        p = resolve(stem)
        with open(p, "rb") as fh:
            out.append((os.path.basename(p), fh.read(), ident))
    return out


def jarjar_meta(winners, metas, extra):
    """入れ子で入れるものぶんの `META-INF/jarjar/metadata.json` を組む。

    ⚠ **土台の identifier と version は自分で作らない**——元の jar が書いていたものを採る
    （⚠ group を推測すると、Forge の重なり整理が別物として扱う）。
    ⚠ `NEST_AS_IS` の分だけは**当部が包み直したもの**なので、当部の名前で書く
    （⚠ 他の MOD が同じ物を入れ子で持っていないことを確かめてある）。
    """
    out = []
    for name, _raw, _src in winners:
        m = metas.get(name)
        if m is None:
            raise SystemExit(
                "!! `%s` の jarjar metadata が元の jar に無い。⚠ **推測で作らない。**" % name)
        m = dict(m)
        m["path"] = "META-INF/jarjar/%s" % name
        out.append(m)
    for name, _raw, ident in extra:
        ver = ".".join(str(x) for x in artifact_of(name)[1]) or "0.0.0"
        out.append({
            "identifier": {"group": ident["group"], "artifact": ident["artifact"]},
            "version": {"range": "[%s,)" % ver, "artifactVersion": ver},
            "path": "META-INF/jarjar/%s" % name,
            "isObfuscated": False,
        })
    return json.dumps({"jars": out}, indent=2, ensure_ascii=False)


def check_mergeable():
    """⚠⚠ **混ぜてよい形か**を作る側で見る（2026-08-30 に起動前で落ちたので足した）。

    ⚠ 見るのは2つ:
      ⑴ `modLoader` が `javafml` か（⚠ 1つの `mods.toml` は1つしか持てない）
      ⑵ class が1つでも在るか（⚠ `lowcodefml` は 0 個で、`@Mod` のクラスが無い）
    """
    bad = []
    for stem in TOP:
        p = resolve(stem)
        with zipfile.ZipFile(p) as z:
            t = z.read("META-INF/mods.toml").decode("utf-8", "replace")
            m = re.search(r'^\s*modLoader\s*=\s*["\']([^"\']+)', t, re.M)
            loader = m.group(1) if m else "（宣言なし）"
            ncls = sum(1 for n in z.namelist() if n.endswith(".class"))
        if loader != "javafml" or ncls == 0:
            bad.append((os.path.basename(p), loader, ncls))
    return bad


def read_metas():
    """元の jar が書いている `jarjar/metadata.json` を、入れ子の jar 名で引けるようにする。"""
    metas = {}

    def walk(blob):
        with zipfile.ZipFile(blob) as z:
            try:
                d = json.loads(z.read("META-INF/jarjar/metadata.json").decode("utf-8"))
                for j in d.get("jars", []):
                    metas[os.path.basename(j.get("path", ""))] = j
            except KeyError:
                pass
            for n in z.namelist():
                if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                    walk(io.BytesIO(z.read(n)))

    for stem in TOP:
        with open(resolve(stem), "rb") as fh:
            walk(io.BytesIO(fh.read()))
    return metas


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


def impl_version_of(blob):
    """MANIFEST の `Implementation-Version` を採る（無ければ None）。"""
    for line in blob.decode("utf-8", "replace").replace("\r\n", "\n").split("\n"):
        if line.startswith("Implementation-Version:"):
            return line.split(":", 1)[1].strip()
    return None


def substitute_jar_version(label, text, impl):
    """⚠⚠ **`${file.jarVersion}` を、その jar の本当の版で埋める。**

    ⚠ **なぜ要るか（2026-09-01 に実機で捕まえた）**: Forge はこの書き方を
    ⚠ **jar の MANIFEST の `Implementation-Version` から**解決する
    （`fmlloader` の `net/minecraftforge/fml/loading/moddiscovery/ModFile.class` に
    `jarVersion` と `0.0NONE` の両方の文字列が在る）。

    ⚠⚠ **ところが混ぜた jar の MANIFEST は 1 つしか無い。**
    ⚠ 元の 6 本は別々の `Implementation-Version` を持っているので、
    ⚠ **どれか 1 つを残しても、残りは嘘になる。**

    ⚠ 実際に `originsumbrellas` と `shiftingorigins` の版が **`0.0NONE`** になり、
    ⚠⚠ **サーバは何事も無く動き、ログの 1 行だけが違っていた**（誰も気づかなかった）。

    ⇒ ⚠ **MANIFEST に頼るのをやめ、混ぜる時点で実数へ置き換える。**
    ⚠ こうすると `[[mods]]` ごとに本当の版が残り、MANIFEST が 1 つでも困らない。
    """
    if "${file.jarVersion}" not in text:
        return text
    if not impl:
        raise SystemExit(
            "!! `%s` は `version=\"${file.jarVersion}\"` と書いているのに、\n"
            "⚠ その jar の MANIFEST に `Implementation-Version` が無い。\n"
            "⚠⚠ **推測で埋めない。** 元の jar を直すか、`mods.toml` に実数を書く。" % label)
    print("   版を埋めた: %-46s ${file.jarVersion} → %s" % (label, impl))
    return text.replace("${file.jarVersion}", impl)


def merge_mods_toml(texts):
    """`[[mods]]` と `[[dependencies.*]]` を全部並べる。⚠ 前置きは最初の1本から採る。

    ⚠⚠ **`license=` だけは書き換える**（合わせた中身を全部並べる）。
    ⚠⚠ **`${file.jarVersion}` は呼ぶ側で埋めてある**（`substitute_jar_version`）。
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


def packages_of(names):
    """class の入り口から package を作る（`a/b/C.class` → `a.b`）。"""
    out = set()
    for n in names:
        if n.endswith(".class") and "/" in n:
            out.add(n.rsplit("/", 1)[0].replace("/", "."))
    return out


def other_mod_packages():
    """⚠⚠ **当部の一族以外**の MOD が出す package を全部集める（入れ子も含む）。

    ⚠ **なぜ要るか（2026-08-30 に踏んだ）**: 土台を溶かして混ぜたら、遊び用サーバが
    ⚠ **起動前に落ちた**——

        java.lang.module.ResolutionException:
          Modules origins and mixinextras export package
          com.llamalad7.mixinextras.platform.forge to module ...

    ⚠ Forge は jar を1つずつ**モジュール**として載せるので、
    ⚠⚠ **同じ package を2つのモジュールが出すと、そこで終わる。**
    ⚠ `mixinextras` は**他の MOD 30 本**が入れ子で持っていた。

    ⚠ **一族7本の中だけを見て「class 衝突 0 件」と言っていたのが穴だった。**
    ⚠ 走査の範囲が狭いと、0 件は何も言っていない。
    """
    mine = {os.path.basename(resolve(s)) for s in TOP}
    mine |= {os.path.basename(resolve(s)) for s in NEST_AS_IS}
    # ⚠⚠ **自分の出力も除く。** ⚠ 2026-08-30 に、入れ替えた後の `instance/mods` に
    #    ⚠ **前に置いた当部の jar が居て**、⚠ **自分自身と 82 個ぶつかると出した。**
    mine |= {f for f in os.listdir(MODS) if f.startswith("eruto-origins-")}
    out = collections.defaultdict(set)

    def walk(blob, label):
        with zipfile.ZipFile(blob) as z:
            names = z.namelist()
            for p in packages_of(names):
                out[p].add(label)
            for n in names:
                if n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                    walk(io.BytesIO(z.read(n)), "%s ▸ %s" % (label, os.path.basename(n)))

    for f in sorted(os.listdir(MODS)):
        if not f.endswith(".jar") or f in mine:
            continue
        try:
            with open(os.path.join(MODS, f), "rb") as fh:
                walk(io.BytesIO(fh.read()), f)
        except Exception:
            continue
    return out


def check_packages(entries):
    """⚠ 当部の jar が**外へ出す** package が、他の MOD とぶつからないか。

    ⚠ 入れ子で入れる土台は**数えない**（あちらは別のモジュールとして載り、
    ⚠ 重なりは Forge が整理する）。数えるのは**溶かした分だけ**。
    """
    mine = packages_of(entries)
    others = other_mod_packages()
    clash = sorted(p for p in mine if p in others)
    return mine, clash, others


def run(write=False):
    drop = mor_drop()
    sink, chosen, dropped, winners = gather()
    entries = sink["entries"]

    print("== 入れた jar ==")
    for stem in TOP:
        print("   %s" % os.path.basename(resolve(stem)))
    print("== 入れ子のまま入れる土台（⚠ 高いほうを採る）==")
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

    # ⚠⚠ **混ぜてよい形か**（modLoader と class の有無）
    notok = check_mergeable()
    if notok:
        print("== ⚠⚠ 混ぜてはいけない形の jar が %d 本 ==" % len(notok))
        for name, loader, ncls in notok:
            print("   !! %-52s modLoader=%s class %d 個" % (name, loader, ncls))
        print("⚠ **`modLoader` は 1 つの `mods.toml` に 1 つだけ。**")
        print("⚠ `NEST_AS_IS` へ移して**入れ子のまま**入れる。")
        bad.append(("(混ぜてはいけない形 %d 本)" % len(notok), ["起動前に落ちる"]))

    # ⚠⚠ **モジュールの衝突を作る側で見る**（2026-08-30 に起動前で落ちたので足した）
    mine_pkgs, clash, others = check_packages(entries)
    print("   ⚠ 当部が出す package %d 個 ／ 他の MOD が出す package %d 個 ／ "
          "⚠⚠ **ぶつかり %d 個**" % (len(mine_pkgs), len(others), len(clash)))
    if clash:
        print("== ⚠⚠ 同じ package を出す MOD が他に居る（Forge は起動前に落ちる）==")
        for p in clash[:15]:
            print("   !! %-52s ← %s" % (p, ", ".join(sorted(others[p])[:3])))
        if len(clash) > 15:
            print("   … 他 %d 個" % (len(clash) - 15))
        print("⚠ **その土台は溶かさず、入れ子のまま入れる**（重なりの整理は JarJar の仕事）。")
        bad.append(("(package の衝突 %d 個)" % len(clash), ["起動前に落ちる"]))

    # ⚠⚠ **相手の名前空間へ書いている分**（ぶつかっていなくても出す）
    cross = check_cross_namespace(entries)
    unex = [c for c in cross if c[2] is None]
    print("   ⚠⚠ **相手の名前空間へ書いている data: %d 件**（うち説明なし %d 件）"
          % (len(cross), len(unex)))
    if cross:
        print("== ⚠ 相手の領分へ入っている data ==")
        for n, label, why in cross:
            print("   %s %-52s ← %s" % ("  " if why else "!!", n, label))
            print("        %s" % (why or "⚠⚠ **説明が無い。追いかけが要る状態のまま。**"))
    if unex:
        print("⚠ **なぜ相手の名前空間へ書くのかを `CROSS_NS_OK` に書くまで作らない。**")
        print("⚠ 書けないなら、⚠⚠ **その定義を持ち主の側へ畳む**のが本筋。")
        bad.append(("(相手の名前空間へ %d 件)" % len(unex), ["追いかけが残る"]))

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
                # ⚠⚠ **`${file.jarVersion}` を、その jar の MANIFEST の版で埋めてから混ぜる。**
                #    ⚠ 混ぜた jar の MANIFEST は 1 つしか無いので、後からでは解決できない。
                impls = {l: impl_version_of(b)
                         for l, b in entries["META-INF/MANIFEST.MF"]}
                toml, lics, combined = merge_mods_toml(
                    [(l, substitute_jar_version(l, b.decode("utf-8", "replace"),
                                                impls.get(l)))
                     for l, b in owners])
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
        # ⚠⚠ **土台は入れ子のまま入れる。** 溶かすと他の MOD とモジュールがぶつかる。
        metas = read_metas()
        extra = nest_as_is()
        for name, raw, _src in winners:
            z.writestr("META-INF/jarjar/%s" % name, raw)
        for name, raw, _ident in extra:
            z.writestr("META-INF/jarjar/%s" % name, raw)
        z.writestr("META-INF/jarjar/metadata.json", jarjar_meta(winners, metas, extra))
        print("   入れ子で入れた: 土台 %d 本 ＋ 混ぜない MOD %d 本"
              % (len(winners), len(extra)))
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

    # ⚠⚠ package の衝突を見る側の対照（2026-08-30 に起動前で落ちた形）
    sink0, _c0, _d0, _w0 = gather()
    mine, clash, others = check_packages(sink0["entries"])
    HIT = "com.llamalad7.mixinextras.platform.forge"
    if HIT in others:
        print("  ok 陽性 他の MOD %d 本が %s を出しているのが見えている"
              % (len(others[HIT]), HIT))
    else:
        print("  NG 陽性 %s が見えていない（走査の範囲が狭い）" % HIT)
        ng += 1
    if HIT in mine:
        print("  NG 陰性 当部の jar が %s を出している（また落ちる）" % HIT)
        ng += 1
    else:
        print("  ok 陰性 当部の jar は %s を出していない" % HIT)
    if clash:
        print("  NG いまの構成で package が %d 個ぶつかる" % len(clash))
        ng += 1
    else:
        print("  ok いまの構成で package のぶつかりは 0 個")

    # ⚠⚠ 相手の名前空間へ書いている分を見る側の対照（2026-09-01・あなたの指摘）
    cross = check_cross_namespace(sink0["entries"])
    if len(cross) >= 5:
        print("  ok 陽性 相手の名前空間へ書いている data を %d 件つかまえた" % len(cross))
    else:
        print("  NG 陽性 %d 件しか見えない（5 件在るはず）" % len(cross))
        ng += 1
    unex = [c for c in cross if c[2] is None]
    if unex:
        print("  NG 説明の無い越境が %d 件" % len(unex))
        ng += 1
    else:
        print("  ok 越境 %d 件すべてに理由が書いてある" % len(cross))
    # ⚠ 陽性: **説明を外すと鳴る**こと（許し一覧が効きすぎて黙る壊れ方を見る）
    keep = dict(CROSS_NS_OK)
    CROSS_NS_OK.clear()
    left = [c for c in check_cross_namespace(sink0["entries"]) if c[2] is None]
    CROSS_NS_OK.update(keep)
    if left:
        print("  ok 陽性 説明を外すと %d 件が「説明なし」に化ける" % len(left))
    else:
        print("  NG 陽性 説明を外しても鳴らない（許しが効きすぎている）")
        ng += 1

    # ⚠ 陰性: 決めた表の宛先が、実際にその入り口を持っていること
    sink, _c, _d, _w = gather()
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
