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

# ⚠⚠ **段4: 当部の datapack を jar の中へ入れる**（2026-09-01）。
#
# ⚠ **なぜ（依頼者の意向）**: 「⚠ 複数の MOD や datapack に散らばってしまったものを
# ⚠⚠ **1つの MOD に1つの実装として**まとめれば管理もしやすくバグもなくなる」。
#
# ⚠ いま能力の定義は **jar と datapack の2か所**に在り、⚠⚠ **どちらが勝つかは
# `loading_priority` が実行時に決めている**（＝設計書 §3 が「やめる」と言った形）。
# ⚠ jar へ入れれば **1か所**になり、⚠ **ワールドを作り直しても消えない**（問題8）。
#
# ⚠⚠ **入れると 85 件がぶつかる。** 足し合わせの種類は `MERGERS` が合わせ、
# ⚠ 選ぶ種類は `DECIDED` が理由を要求する。⚠ **どちらでもない物が在れば作れない。**
#
# ⚠ **`--no-datapacks` で外せる**（段4 の前後を比べるため）。
DATAPACKS = [
    os.path.join(MC, "worlds", "world-3", "datapacks", "origins_setup", "src"),
    os.path.join(MC, "worlds", "world-3", "datapacks", "origins_diet", "src"),
]
USE_DATAPACKS = True


def datapack_entries():
    """datapack の `data/**` を (見出し, 入り口, 中身) で返す。⚠ `pack.mcmeta` は入れない。"""
    out = []
    if not USE_DATAPACKS:
        return out
    for root in DATAPACKS:
        if not os.path.isdir(root):
            raise SystemExit("!! datapack の置き場が無い: %s" % root)
        label = "datapack:" + os.path.basename(os.path.dirname(root))
        n = 0
        for dp, _dn, fs in os.walk(os.path.join(root, "data")):
            for f in fs:
                p = os.path.join(dp, f)
                rel = os.path.relpath(p, root).replace(os.sep, "/")
                with open(p, "rb") as fh:
                    out.append((label, rel, fh.read()))
                n += 1
        print("   ⚠ %s から %d 件を入れる" % (label, n))
    return out


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
    # ⚠⚠ **2026-09-01・段4 で外した3件。** ⚠ **前提が消えたため**（自分で注記に書いていた）。
    #
    # ⚠ 段4 の前は「datapack が**後から**読まれて勝つので、jar 側でどちらを採っても同じ」だった。
    # ⚠⚠ **jar へ入れた瞬間、その「後から」が無くなる**——同じ zip の中に1つしか置けないので、
    # ⚠ ここで上流を採ると**当部の定義が消える。**
    #
    # ⚠ 外した3件（`DECIDED` から消して、規則に任せた）:
    #   `data/origins/origin_layers/origin.json`   … ⚠ 上流10種 対 当部17種（`replace:true`）
    #   `data/origins/powers/light_armor.json`     … ⚠ 優先度 0 対 200
    #   `data/origins/powers/claustrophobia.json`  … ⚠ 同上
    #
    # ⚠ 層は `LOSSY_OK` が、能力は `pick_by_priority` が受け持つ。
    # ⚠⚠ **どちらも Minecraft と同じ決め方**なので、当部が手で決めるより間違えにくい。
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
    "data/origins-classes/powers/explorer_kit.json": (
        "shifting_origins",
        "⚠ ここだけ**本物の上書き**（同じ中身の組が無い）。当部の物を採る"),
    # ── 段4（当部の datapack を jar へ入れる）で出たぶつかり（2026-09-01）──
    #
    # ⚠ **`loading_priority` が無い種類**なので、道具は決められない。⚠ 1件ずつ開いて決めた。
    # ⚠ **どれも「当部が意図して上書きしている物」**——datapack が後に読まれて勝っており、
    # ⚠⚠ **jar へ入れても同じ結果にするには datapack の側を採る。**
    "data/medievalorigins/functions/mdvlorigins/arachnae_extricate.mcfunction": (
        "datapack:origins_setup",
        "⚠ 当部が短くした版（6行 → 4行）。⚠ **いまも datapack が勝っている**ので、"
        "同じ結果にするには当部の物を採る"),
    "data/medievalorigins/functions/mdvlorigins/pixie_callon.mcfunction": (
        "datapack:origins_setup",
        "⚠ 当部が縮尺を変えた版（`pehkui:height` 0.166 → 0.444）。同上"),
    "data/origins-classes/origin_layers/class.json": (
        "datapack:origins_setup",
        "⚠⚠ **当部の層の定義**（`default_origin`・`allow_random`・`name`・"
        "`missing_name` ほかを持つ。上流は4項目、当部は10項目）。"
        "⚠ `replace` を持つので**丸ごと置き換えが決まり**——当部の物を採る"),
    "data/origins/badges/active.json": (
        "datapack:origins_setup",
        "⚠ 当部が印の文言を差し替えた分。同上"),
    "data/origins/badges/toggle.json": (
        "datapack:origins_setup",
        "⚠ 当部が印の文言を差し替えた分。同上"),
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
    # ⚠ 段4 で `DECIDED` から外した3件の越境の理由（2026-09-01）。
    #    ⚠ **越境そのものは前から在り**、`DECIDED` の理由文が兼ねていた。
    #    ⚠⚠ **決着（どれを採るか）と越境（誰の領分か）は別の問い**なので、分けて書く。
    "data/origins/origin_layers/origin.json":
        "⚠ MOR が `origins` の層へ自分の19種族を足している（`replace:false`）。"
        "⚠⚠ **層は足し合わせなので、これは正しい書き方**。"
        "⚠ 当部は `replace:true` の1枚で畳むので、合成の結果に含まれる",
    "data/origins/powers/light_armor.json":
        "⚠ `shifting_origins` が `origins` の能力を上書きしている"
        "（優先度100・`hidden`＝当部で無効化した版）。"
        "⚠⚠ **当部の `origins_setup` が優先度200 で有効へ戻す**ので、"
        "`pick_by_priority` が 200 の側を採る（2026-08-29 の決定）",
    "data/origins/powers/claustrophobia.json":
        "同上（⚠ 優先度 0 / 100 / 200 の3枚が在り、200 が勝つ）",
    "data/forge/tags/damage_types/is_magic.json":
        "⚠ Forge の共有タグ。⚠ **タグは上書きではなく足し合わせ**なので、"
        "他の MOD の分を消さない（追いかけが要らない）",
}

# ⚠⚠ **訳の鍵が2つの名前空間にまたがっているとき、どちらを正とするか**（2026-09-01 新設）。
#
# ⚠ **なぜ要るか**: 翻訳の鍵は**名前空間で分かれていない**。
# ⚠ `ClientLanguage.loadFrom` が全名前空間を**1枚の平らな Map** へ流し込み、同じ鍵は後勝ち
# （逆コンパイルした `net/minecraft/client/resources/language/ClientLanguage.java:32-49` を開いて確認）。
#
# ⚠⚠ **その巡回順は `MultiPackResourceManager.getNamespaces()` ＝ `HashMap.keySet()`**
# （同 `net/minecraft/server/packs/resources/MultiPackResourceManager.java:26,72-74`）。
# ⚠⚠ **つまり順序は決まっていない。** MOD を足し引きすれば入れ替わる。
#
# ⚠ **これは設計書 §3 が「無くす」と言った状態そのもの**——
# 「⚠ 同じ id が2つ在れば、いまのように静かに勝敗が決まるのではなく、ビルドが落ちるようにする」。
# ⚠ だから**混ぜるときに落とす**。値は「勝たせる名前空間」と理由。
LANG_DECIDED = {
    "origin.origins.human.description": (
        "origins",
        "⚠ `origins:human` は **Origins の種族**で、⚠⚠ **MOR が他所の名前空間の鍵を"
        "自分の lang に書いている**（en_us / ja_jp / ru_ru / zh_cn の4言語）。"
        "⚠ MOR 側を落とす——⚠ **MOR 自身の種族（`origin.medievalorigins.*`）の訳は残る**ので、"
        "失う機能は無い。⚠ 当部の手書きの訳は `origins` 名前空間に在るので、そちらが生きる"),
}

MANIFEST_KEEP = ("Manifest-Version",)

# ⚠⚠ **Minecraft は同じパスの data を3通りで解決する**（2026-09-01 に実物のソースで確かめた）。
#
# | 種類 | 決まり方 | 根拠 |
# | - | - | - |
# | `powers/*.json`       | `.max(loading_priority)` 丸ごと1つ勝ち | `apoli/…/PowerLoader.java` |
# | `origins/*.json`      | 同じく丸ごと1つ勝ち                    | `origins/…/OriginLoader.java` |
# | `origin_layers/*.json`| ⚠ **欄ごとの合成**（`replace:true` で置き換え） | `origins/…/LayerLoader.java` |
# | `tags/**.json`        | ⚠ **足し合わせ**（`replace:true` で `list.clear()`） | `net/minecraft/tags/TagLoader.java` |
#
# ⚠⚠ **`DECIDED` は「どちらを採るか」しか書けない。**
# ⚠ 上2つには正しい答えだが、⚠⚠ **下2つには「どちらか」という答えが存在しない**——
# ⚠ 1つに畳んだ時点で、採らなかった側の値は**消える**。
#
# ⚠ だから種類を見分けて、⚠ **足し合わせの種類で値が消えるなら落とす。**
UNION_TAG = "tags"
UNION_LAYER = "origin_layers"
PICK_ONE = "pick"


def merge_kind(path):
    """その data がどう解決されるか。⚠ 分からないものは `None`（＝人に決めさせる）。"""
    p = path.split("/")
    if len(p) < 3 or p[0] != "data":
        return None
    if "/tags/" in path:
        return UNION_TAG
    if UNION_LAYER in p:
        return UNION_LAYER
    if "powers" in p or "origins" in p[2:]:
        return PICK_ONE
    return None


def tag_values(blob):
    """タグの `values` を id の一覧にする。読めなければ None。"""
    try:
        d = json.loads(blob.decode("utf-8-sig"))
    except Exception:
        return None, None
    if not isinstance(d, dict) or "values" not in d:
        return None, None
    out = []
    for x in d.get("values", []):
        out.append(x if isinstance(x, str) else (x or {}).get("id"))
    return bool(d.get("replace")), [x for x in out if x]


def layer_origins(blob):
    """層の `origins` を一覧にする。読めなければ None。"""
    try:
        d = json.loads(blob.decode("utf-8-sig"))
    except Exception:
        return None, None
    if not isinstance(d, dict):
        return None, None
    out = []
    for x in d.get("origins", []):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            out.extend(x.get("origins", []) or [])
    return bool(d.get("replace")), out


UNION_LANG = "lang"


def merge_kind_any(path):
    """`data/` だけでなく `assets/**/lang/*.json` も種類として見る。"""
    p = path.split("/")
    if len(p) >= 4 and p[0] == "assets" and p[2] == "lang" and path.endswith(".json"):
        return UNION_LANG
    return merge_kind(path)


def merge_tag(owners):
    """⚠⚠ **タグを足し合わせる**（1つ選ばない）。

    ⚠ Minecraft は `replace:false` のタグを**全部の pack から足す**
    （`net/minecraft/tags/TagLoader.java`——`replace` が真なら `list.clear()`）。
    ⚠ 1つの jar に畳むとその足し算が起きないので、⚠ **ここで先にやっておく。**

    ⚠ **順序は入力の順**（`TOP` の並び）。⚠ `replace:true` が来たら、そこまでを捨てる。
    """
    values, replaced_by = [], None
    for label, blob in owners:
        try:
            d = json.loads(blob.decode("utf-8-sig"))
        except Exception:
            return None, "⚠ 読めない（形が違う）"
        if not isinstance(d, dict) or "values" not in d:
            return None, "⚠ `values` が無い"
        if d.get("replace"):
            values, replaced_by = [], label      # ⚠ そこまでの寄与を捨てる決まり
        for v in d.get("values", []):
            if v not in values:                  # ⚠ 重複は入れない（同じ id が2回出ても害は無いが読みにくい）
                values.append(v)
    out = {"replace": False, "values": values}
    note = ("⚠ `%s` の `replace:true` で、それより前の分は捨てた" % replaced_by
            if replaced_by else "")
    return json.dumps(out, indent=2, ensure_ascii=False).encode("utf-8"), note


def merge_lang(owners):
    """⚠⚠ **訳を鍵ごとに合わせる**（ファイルを1つ選ばない）。

    ⚠ 同じ鍵が両方に在れば**後の入力が勝つ**。⚠ 片方にしか無い鍵は**両方とも残る。**
    ⚠ **これが「1つ選ぶ」との違い**——選ぶと、選ばなかった側だけが持つ鍵が丸ごと消える。
    """
    out, notes = {}, []
    for label, blob in owners:
        try:
            d = json.loads(blob.decode("utf-8-sig"))
        except Exception:
            return None, "⚠ 読めない（形が違う）"
        if not isinstance(d, dict):
            return None, "⚠ 地図の形ではない"
        over = [k for k in d if k in out and out[k] != d[k]]
        if over:
            notes.append("%s が %d 鍵を上書き" % (label, len(over)))
        out.update(d)
    return (json.dumps(out, indent=2, ensure_ascii=False).encode("utf-8"),
            "／".join(notes))


def merge_layer(owners):
    """⚠⚠ **層を欄ごとに合わせる**（`origins/…/api/data/PartialLayer.java` の `merge` と同じ決まり）。

    ⚠ `loading_priority` の小さい順に畳む。⚠ **欄は「後の寄与が値を持っていれば後が勝つ」。**
    ⚠⚠ **`origins` は足し合わせ**——ただし ⚠ **`replace:true` の寄与が来たら、そこまでを捨てる。**

    ⚠ **上流の規則を写している。** ⚠ 写しであることを承知で書く理由:
    ⚠⚠ **1つの zip に2枚置けない以上、ここで畳むしかない。**
    ⚠ 上流が規則を変えたら、⚠ **ここも直す**（`PartialLayer.merge` を見る）。
    """
    SCALAR = ("order", "enabled", "name", "missing_name", "missing_description",
              "allow_random", "allow_random_unchoosable", "default_origin",
              "auto_choose", "hidden", "title")
    got = []
    for label, blob in owners:
        try:
            d = json.loads(blob.decode("utf-8-sig"))
        except Exception:
            return None, "⚠ 読めない（形が違う）"
        if not isinstance(d, dict):
            return None, "⚠ 地図の形ではない"
        got.append((int(d.get("loading_priority", 0)), label, d))
    got.sort(key=lambda g: g[0])          # ⚠ 小さい順に畳む（後が勝つ）

    out, origins, excl, notes = {}, [], [], []
    for _p, label, d in got:
        for k in SCALAR:
            if k in d:
                out[k] = d[k]
        if d.get("replace"):
            origins = []
            notes.append("%s の `replace:true` でそれより前の種族を捨てた" % label)
        for o in d.get("origins", []):
            if o not in origins:
                origins.append(o)
        if d.get("replace_exclude_random"):
            excl = []
        for e in d.get("exclude_random", []):
            if e not in excl:
                excl.append(e)
    out["origins"] = origins
    if excl:
        out["exclude_random"] = excl
    out["replace"] = True                 # ⚠ 畳んだ結果が正。他の寄与を足させない
    return (json.dumps(out, indent=2, ensure_ascii=False).encode("utf-8"),
            "／".join(notes))


# ⚠ 種類 → 合わせ方。⚠ **ここに無い種類は「1つ選ぶ」のまま**（それが正しい種類）。
MERGERS = {
    UNION_TAG: merge_tag,
    UNION_LANG: merge_lang,
    UNION_LAYER: merge_layer,
}


def pick_by_priority(owners):
    """⚠⚠ **`loading_priority` の最大を採る**——Minecraft と同じ決め方（2026-09-01）。

    ⚠ **根拠（ソースで確かめた）**:
      * `apoli/…/common/data/PowerLoader.java` … `.max(LOADING_ORDER_COMPARATOR)`
      * `origins/…/common/data/OriginLoader.java` … `.max(LOADING_ORDER)`
    ⚠ **丸ごと1つが勝つ**（欄ごとの合成ではない）ので、⚠ **勝者を残せば結果は同じ。**

    ⚠ **手で決めない理由**: 82 件在り、⚠⚠ **どれも「datapack が優先度で勝っている」だけ。**
    ⚠ 人が82行書くと、⚠ **1行間違えても誰も気づかない。**

    ⚠ **同点なら決めない**（`None` を返す）——⚠ その場合はいまも
    「どちらが勝つか読み込み順で決まる」状態なので、⚠⚠ **人が決めるべき。**

    返り値: (採る中身, 採った見出し, 優先度の一覧) ／ 決められなければ (None, None, 一覧)
    """
    got = []
    for label, blob in owners:
        try:
            d = json.loads(blob.decode("utf-8-sig"))
        except Exception:
            return None, None, None
        if not isinstance(d, dict):
            return None, None, None
        got.append((int(d.get("loading_priority", 0)), label, blob))
    tops = [g for g in got if g[0] == max(g2[0] for g2 in got)]
    prios = ", ".join("%s=%d" % (l, p) for p, l, _b in got)
    if len(tops) != 1:
        return None, None, prios          # ⚠ 同点＝人が決める
    return tops[0][2], tops[0][1], prios


def strip_priority(path, blob):
    """⚠⚠ **混ぜ終わったら `loading_priority` を消す**（2026-09-01・依頼者の指摘）。

    ⚠ **なぜ**: 「⚠ 優先度で対応しようとすると、⚠⚠ **複雑な CSS 構造みたいな
    修正の難しさ**が生まれる」。⚠ そのとおりで、⚠ **1つのファイルを開いても
    何が勝つか分からない**——統合の目的そのものに反する。

    ⚠⚠ **1つの zip の中に同じパスは1つしか置けないので、優先度は競う相手を持たない。**
    ⚠ 残しても効かないのに、⚠ **読む人には「まだ競っている」ように見える。**

    ⚠ **消せるのは、混ぜる側が決着を済ませたから**——`pick_by_priority` が
    ⚠ **Minecraft と同じ規則で勝者を選び切っている**ので、結果は変わらない。

    ⚠ **例外は無い**（`powers` / `origins` / `origin_layers` のどれでも消す）。
    ⚠ 消したことは件数で必ず出す（黙って書き換えない）。
    """
    kind = merge_kind(path)
    if kind not in (PICK_ONE, UNION_LAYER):
        return blob, False
    if b"loading_priority" not in blob:
        return blob, False
    try:
        d = json.loads(blob.decode("utf-8-sig"))
    except Exception:
        return blob, False
    if not isinstance(d, dict) or "loading_priority" not in d:
        return blob, False
    d.pop("loading_priority")
    return json.dumps(d, indent=2, ensure_ascii=False).encode("utf-8"), True


def lost_by_picking(path, owners, winner_label):
    """⚠⚠ **1つ選んだせいで消える値**を数える。返り値: (種類, 消える値の一覧, 説明)。

    ⚠ 足し合わせの種類でだけ意味がある。⚠ **勝つ側が `replace:true` なら、
    そもそも他の寄与は捨てられる決まりなので、畳んでも結果は変わらない。**
    """
    kind = merge_kind(path)
    if kind not in (UNION_TAG, UNION_LAYER):
        return kind, [], ""
    read = tag_values if kind == UNION_TAG else layer_origins
    win = next((b for l, b in owners if l.startswith(winner_label)), None)
    if win is None:
        return kind, [], "⚠ 勝つ側が見つからない"
    w_replace, w_vals = read(win)
    if w_vals is None:
        return kind, [], "⚠ 中身を読めない（形が違う）"
    if w_replace:
        return kind, [], "⚠ 勝つ側が `replace: true`＝他の寄与は元から捨てられる"
    lost = []
    for label, blob in owners:
        if label.startswith(winner_label):
            continue
        _r, vals = read(blob)
        for v in (vals or []):
            if v not in w_vals and v not in lost:
                lost.append(v)
    return kind, lost, ""


# ⚠⚠ **値が消えると分かっていて、それでも1つ選ぶもの**（2026-09-01 新設）。
#    ⚠ **既定は落とす。** ここに書くのは、⚠ **なぜ消えても平気かを外の事実で言えるとき**だけ。
#    ⚠ **その外の事実が消えたら、この行も無効になる**——だからその条件を必ず書く。
LOSSY_OK = {
    "data/origins/origin_layers/origin.json":
        "⚠ 当部の `origins_setup` が同じパスを `replace: true` で持っており、"
        "⚠ **datapack のほうが後に読まれて層を丸ごと置き換える**ので、"
        "jar 側でどちらを採っても画面には出ない。"
        "⚠⚠ **段4で `origins_setup` を jar へ入れた瞬間、この前提は消える**"
        "——そのときは MOR の分と合わせた1枚を作ること",
}


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


def lang_files(entries):
    """`assets/<名前空間>/lang/<言語>.json` を (パス, 名前空間, 言語, 出どころ, 中身) で返す。"""
    out = []
    for n, owners in sorted(entries.items()):
        p = n.split("/")
        if len(p) < 4 or p[0] != "assets" or p[2] != "lang" or not n.endswith(".json"):
            continue
        for label, blob in owners:
            try:
                d = json.loads(blob.decode("utf-8-sig"))
            except Exception:
                continue
            out.append((n, p[1], p[-1][:-len(".json")], label, d))
    return out


def check_lang_collisions(entries):
    """⚠⚠ **2つ以上の名前空間が同じ翻訳の鍵を、違う値で持っていないか。**

    ⚠ 持っていたら、どちらが画面に出るかは `HashMap` の巡回順に任される（`LANG_DECIDED` の注記）。
    ⚠ **同じ値なら問題にしない**（どちらが勝っても同じ文字が出る）。

    返り値: [(言語, 鍵, {(名前空間, 出どころ): 値}, 決めてあるか)]
    """
    per = collections.defaultdict(lambda: collections.defaultdict(dict))
    for _n, ns, code, label, d in lang_files(entries):
        for k, v in d.items():
            per[code][k][(ns, label)] = v
    out = []
    for code in sorted(per):
        for k, owners in sorted(per[code].items()):
            if len({ns for ns, _l in owners}) < 2:
                continue
            if len(set(owners.values())) == 1:
                continue          # ⚠ 値が同じなら、どちらが勝っても画面は変わらない
            out.append((code, k, owners, k in LANG_DECIDED))
    return out


def apply_lang_decision(path, blob):
    """⚠ 負けた名前空間の lang から、決めた鍵を落とす。返り値: (中身, 落とした鍵の一覧)。"""
    p = path.split("/")
    if len(p) < 4 or p[0] != "assets" or p[2] != "lang":
        return blob, []
    ns = p[1]
    try:
        d = json.loads(blob.decode("utf-8-sig"))
    except Exception:
        return blob, []
    dropped = [k for k, (winner, _why) in LANG_DECIDED.items()
               if k in d and winner != ns]
    if not dropped:
        return blob, []
    for k in dropped:
        del d[k]
    return json.dumps(d, indent=2, ensure_ascii=False).encode("utf-8"), dropped


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

# ⚠⚠ **当部がソースから建てた jar を、配布 jar の代わりに使う**（2026-09-01）。
#
# ⚠ **なぜ要るか**: この道具は配布 jar を混ぜるので、⚠⚠ **段1・段2 の成果が出荷物に入らない。**
# ⚠ 実際に測ったら、出荷している jar の `logPowerTally` を含む class は **0 個**で
# ⚠ （ソースには 3 か所在る）、入れ子の `apoli` は
# ⚠ **2026-07-27 の class を差し替えた写しとバイト一致**だった。
# ⚠ **その状態では段5（珠の画面を直す）ができない**——直しはソースからしか入らない。
#
# ⚠ `origins` の `-all` jar 1 本で、⑴ ソースから建てた `origins` と
# ⑵ ソースから建てた入れ子の `apoli`・`calio` の両方が入る（段1と段2）。
#
# ⚠ 値は「その stem の代わりに使うファイルを探す形」。⚠ **版番号を書かない。**
# ⚠⚠ **当たりが 1 本でなければ落ちる**（黙って別の物を使わない）。
BUILT = {
    # stem → (置き場, 名前の頭, 名前の尻, ⚠ **その jar が反映しているはずのソース**)
    "origins-forge-": (os.path.join(REPO, "origins", "build", "libs"),
                       "origins-forge-", "-all.jar",
                       ["origins/src", "apoli/src", "calio/src"]),
}

# ⚠ `--released` を付けると `BUILT` を使わず、配布 jar だけで混ぜる。
#   ⚠ 段1・段2 の「配っている jar と同じ物が出る」を確かめ直したいときに使う。
USE_BUILT = True


def built_path(stem):
    """`BUILT` に在る stem について、当部が建てた jar を1本に決める。無ければ None。"""
    spec = BUILT.get(stem)
    if not spec or not USE_BUILT:
        return None
    d, head, tail, srcs = spec
    if not os.path.isdir(d):
        raise SystemExit(
            "!! `%s` の建てた jar の置き場が無い: %s\n"
            "⚠ 先に `./gradlew :origins:jarJar` を回す"
            "（⚠ 素の `java` は 8 なので JAVA_HOME に JDK 17 を指す）。" % (stem, d))
    hits = sorted(f for f in os.listdir(d)
                  if f.startswith(head) and f.endswith(tail))
    if len(hits) != 1:
        raise SystemExit(
            "!! `%s` に当たる建てた jar が %d 本（1本でないと使えない）: %s\n"
            "⚠ **黙って選ばない。** 要らない物を消すか `BUILT` を直す。"
            % (stem, len(hits), ", ".join(hits) or "無し"))
    p = os.path.join(d, hits[0])

    # ⚠⚠ **建てた物がソースより古ければ落とす**（2026-09-01）。
    #    ⚠ **なぜ要るか**: `./gradlew :origins:jarJar` は AEA の解決で落ちるのに、
    #    ⚠⚠ **前の走行の `-all.jar` がそのまま残る。** 私はそれを見ずに
    #    「ビルドが通った」と報告し、⚠ **11日前の jar を入力にしかけた。**
    #    ⚠ 当部の規則「⚠ 『書き出した／ビルドした』と言う → 成果物の更新時刻も見る」を機械にした。
    jar_mt = os.path.getmtime(p)
    newest, newest_f = 0.0, None
    for rel in srcs:
        root = os.path.join(REPO, *rel.split("/"))
        for dp, _dn, fs in os.walk(root):
            for f in fs:
                if not f.endswith((".java", ".json", ".mcmeta", ".png", ".cfg")):
                    continue
                mt = os.path.getmtime(os.path.join(dp, f))
                if mt > newest:
                    newest, newest_f = mt, os.path.join(dp, f)
    if newest_f and newest > jar_mt + 1:
        import time
        raise SystemExit(
            "!! 建てた jar がソースより古い。⚠ **古い物から作らない。**\n"
            "   jar    : %s（%s）\n"
            "   ソース : %s（%s）\n"
            "⚠ `./gradlew :origins:jarJar` を回し直す。⚠⚠ **終了コードだけを見ない**"
            "——ログの最後が `BUILD SUCCESSFUL` か、jar の更新時刻が新しくなったかの両方を見る。\n"
            "⚠ 配布 jar だけで作りたいなら `--released` を付ける。"
            % (os.path.relpath(p, REPO).replace("\\", "/"),
               time.strftime("%m-%d %H:%M", time.localtime(jar_mt)),
               os.path.relpath(newest_f, REPO).replace("\\", "/"),
               time.strftime("%m-%d %H:%M", time.localtime(newest))))
    return p


def resolve(stem):
    """元の jar を1本に決める。

    ⚠⚠ **退避先も見る。** ⚠ 2026-08-30 に、入れ替えた後は `instance/mods` に元の jar が
    無いので**作り直せなかった**（試験の途中で道具が使えなくなる）。
    ⚠ 退避先には**古い版も居る**ので、⚠ **版が最大の1本**を採り、そのことを印字する。

    ⚠⚠ **当部が建てた jar が在るならそちらが先**（`BUILT`）。⚠ **必ず印字する。**
    """
    b = built_path(stem)
    if b:
        print("   ⚠ %s は**当部が建てた物**を使う（%s）"
              % (os.path.basename(b), os.path.relpath(b, REPO).replace("\\", "/")))
        return b
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
    # ⚠⚠ **段4: 当部の datapack を最後に足す**（2026-09-01）。
    #    ⚠ **順序が意味を持つ**——`MERGERS` の合成は入力の順で、⚠ **後が勝つ**。
    #    ⚠ datapack は当部が上流を上書きするために書いた物なので、⚠ **最後に置く。**
    for label, rel, blob in datapack_entries():
        sink["entries"].setdefault(rel, []).append((label, blob))
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
    # ⚠⚠ **除くのは「名前の頭」で見る。解決した実体の名前で見ない**（2026-09-01 に直した）。
    #    ⚠ `BUILT` で当部が建てた jar を入力にした瞬間、⚠ **解決した名前が
    #    `…-all.jar`（`-eruto1` が付かない）に変わり、`instance/mods` に残っている
    #    配布 jar と一致しなくなった。** ⚠⚠ **結果、自分自身と 38 個ぶつかると出した。**
    #    ⚠ 2026-08-30 に同じ形を1度踏んでいる（前に置いた当部の jar と 82 個）。
    #    ⚠ **名前の頭で除けば、入力をどこから採っても効く。**
    stems = tuple(TOP) + tuple(NEST_AS_IS) + ("eruto-origins-",)
    mine = {f for f in os.listdir(MODS) if f.startswith(stems)}
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
    mergeable = by_priority = 0
    for n, owners in sorted(entries.items()):
        if n in special or len(owners) == 1:
            continue
        blobs = {b for _l, b in owners}
        if len(blobs) == 1:
            continue                       # ⚠ 中身が同じなら問題にしない
        if n in DECIDED:
            continue
        # ⚠⚠ **合わせられる種類は、ぶつかりとして数えない**（`MERGERS` が足し合わせる）。
        if MERGERS.get(merge_kind_any(n)):
            mergeable += 1
            continue
        # ⚠⚠ **1つ選ぶ種類は `loading_priority` で決まる**（Minecraft と同じ決め方）。
        #    ⚠ **同点だけが人の仕事**——いまも読み込み順で決まっている所なので。
        if merge_kind(n) == PICK_ONE:
            _b, who, prios = pick_by_priority(owners)
            if who is not None:
                by_priority += 1
                continue
            bad.append((n, [l for l, _b2 in owners] + ["⚠ 優先度が同点（%s）" % prios]))
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

    # ⚠⚠ **訳の鍵が名前空間をまたいでぶつかっていないか**（2026-09-01 追加）
    #    ⚠ 同じパスでぶつからないので `DECIDED` では捕まらない。
    #    ⚠ **どちらが出るかが `HashMap` の巡回順に任される**＝設計書 §3 が無くすと言った状態。
    lang_bad = check_lang_collisions(entries)
    undecided = [c for c in lang_bad if not c[3]]
    print("   ⚠⚠ **訳の鍵が名前空間をまたいでぶつかっている: %d 件**（うち未決 %d 件）"
          % (len(lang_bad), len(undecided)))
    if lang_bad:
        print("== ⚠ 名前空間をまたぐ訳の重複 ==")
        for code, k, owners, decided in lang_bad:
            print("   %s %-10s %s" % ("  " if decided else "!!", code, k))
            for (ns, label), v in sorted(owners.items()):
                mark = "→" if decided and LANG_DECIDED[k][0] == ns else " "
                print("        %s %-18s ← %-44s %s"
                      % (mark, ns, label, v.replace("\n", "\\n")[:44]))
            if decided:
                print("        %s" % LANG_DECIDED[k][1])
    if undecided:
        print("⚠ **どちらを正とするかを `LANG_DECIDED` に理由つきで書くまで作らない。**")
        print("⚠⚠ **書かないと、画面に出る文が MOD の増減で入れ替わる**"
              "（`getNamespaces()` が `HashMap.keySet()` のため）。")
        bad.append(("(訳の重複 %d 件)" % len(undecided), ["どちらが出るか決まらない"]))

    print("== 決めたぶつかり（%d 件・理由つき）==" % len(DECIDED))
    for n, (who, why) in sorted(DECIDED.items()):
        here = n in entries
        print("   %s %-52s → %s" % ("  " if here else "!!", n, who))
        print("        %s" % why)
        if not here:
            bad.append((n, ["⚠ もう存在しない（決定が古い）"]))
            continue
        # ⚠⚠ **足し合わせの種類なら、1つ選んだせいで消える値を数える**（2026-09-01）。
        #    ⚠ 「どちらを採るか」という答えが存在しない種類なので、黙って選ばせない。
        kind, lost, note = lost_by_picking(n, entries[n], who)
        if kind in (UNION_TAG, UNION_LAYER):
            print("        ⚠ 種類: %s（**足し合わせ**）%s"
                  % (kind, ("／" + note) if note else ""))
            if lost:
                ok = LOSSY_OK.get(n)
                print("        %s **1つ選ぶと消える値: %d 件** %s"
                      % ("  " if ok else "!!", len(lost), lost[:6]))
                if ok:
                    print("        （消えてよい理由）%s" % ok)
                else:
                    bad.append((n, ["⚠ 足し合わせなのに1つ選んで %d 件消える" % len(lost)]))
            else:
                print("        ok 消える値は無い")
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
    lang_dropped = []          # ⚠ 負けた名前空間から落とした訳の鍵（必ず印字する）
    merged_paths = []          # ⚠ 1つ選ばずに**合わせた**入り口（必ず印字する）
    picked_by_priority = []    # ⚠ `loading_priority` で決めた入り口（必ず印字する）
    priority_stripped = []     # ⚠⚠ 決着後に `loading_priority` を消した入り口（必ず印字する）
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
            # ⚠⚠ **合わせられる種類は、選ばずに合わせる**（2026-09-01）。
            #    ⚠ タグと lang は**足し合わせ**なので、1つ選ぶと片方の値が丸ごと消える。
            merger = MERGERS.get(merge_kind_any(n)) if len(owners) > 1 else None
            blob = None
            if merger and len({b for _l, b in owners}) > 1:
                merged, note = merger(owners)
                if merged is not None:
                    merged_paths.append((n, [l for l, _b in owners], note))
                    blob = merged
                else:
                    merged_paths.append((n, [l for l, _b in owners],
                                         "⚠ 合わせられなかった（%s）→ 1つ選ぶ" % note))
            if blob is None:
                pick = DECIDED[n][0] if n in DECIDED else None
                if pick is None and len(owners) > 1 and merge_kind(n) == PICK_ONE:
                    # ⚠⚠ **Minecraft と同じ決め方**（`loading_priority` の最大）。
                    pb, who, _pr = pick_by_priority(owners)
                    if pb is not None:
                        picked_by_priority.append((n, who))
                        blob = pb
                if blob is None:
                    blob = next((b for l, b in owners if pick and l.startswith(pick)),
                                owners[0][1])
                    # ⚠⚠ **負けた名前空間の訳から、決めた鍵を落とす**（2026-09-01）。
                    #    ⚠ 落とした分は必ず印字する（黙って消さない）。
                    blob, dropped_keys = apply_lang_decision(n, blob)
                    for k in dropped_keys:
                        lang_dropped.append((n, k))
            # ⚠⚠ **書き出し口を1つにまとめてある**（2026-09-01）。
            #    ⚠ 以前は3か所に散っており、⚠ **`strip_priority` を足すとき
            #    どれかを直し忘れる形**だった（当部が何度も踏んでいる型）。
            blob, stripped = strip_priority(n, blob)
            if stripped:
                priority_stripped.append(n)
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
    # ⚠⚠ **優先度を消した件数を出す**（黙って書き換えない）。
    if priority_stripped:
        print("   ⚠⚠ 決着後に `loading_priority` を消した: %d 件"
              % len(priority_stripped))
        print("      （⚠ 1つの zip に同じパスは1つしか置けないので、"
              "優先度は競う相手を持たない。⚠ 残すと読む人を惑わせるだけ）")
    # ⚠⚠ **優先度で決めた分を数で出す**（82 件を1件ずつは出さない。⚠ 内訳は下の表）。
    if picked_by_priority:
        import collections as _c
        by = _c.Counter(who for _n, who in picked_by_priority)
        print("   ⚠ `loading_priority` で決めた入り口: %d 件" % len(picked_by_priority))
        for who, cnt in by.most_common():
            print("      %-40s %d 件を採った" % (who, cnt))
    # ⚠⚠ **合わせた入り口を名指しで出す**（1つ選ばなかったことを見えるようにする）。
    if merged_paths:
        print("   ⚠ 1つ選ばずに**合わせた**入り口: %d 件" % len(merged_paths))
        for n, labels, note in sorted(merged_paths):
            print("      %-56s ← %s" % (n, "＋".join(labels)))
            if note:
                print("           %s" % note)
    # ⚠⚠ **落とした訳の鍵を名指しで出す**（黙って消さない）。
    if lang_dropped:
        print("   ⚠ 負けた名前空間から落とした訳の鍵: %d 件" % len(lang_dropped))
        for n, k in sorted(lang_dropped):
            print("      %-44s %s" % (n, k))
    print()
    print("作った: %s（%d バイト）" % (out, os.path.getsize(out)))
    return 0


def self_test():
    print("== 自己試験 ==")
    # ⚠ 自己試験は**配布 jar だけ**で回す（`--released` と同じ）。
    #   ⚠ 当部が建てた jar は在ったり無かったり古かったりするので、
    #   ⚠⚠ **道具の判定を試すのに、入力の都合で落ちると意味が無い。**
    global USE_BUILT
    was, USE_BUILT = USE_BUILT, False
    try:
        return _self_test_body()
    finally:
        USE_BUILT = was


def _self_test_body():
    ng = 0
    print("  ⚠ 入力は配布 jar（`BUILT` は使わない）")
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

    # ⚠⚠ 訳の重複を見る側の対照（2026-09-01・⚠ **設計書 §3 が無くすと言った状態**）
    lang_bad = check_lang_collisions(sink0["entries"])
    if len(lang_bad) >= 4:
        print("  ok 陽性 名前空間をまたぐ訳の重複を %d 件つかまえた" % len(lang_bad))
    else:
        print("  NG 陽性 %d 件しか見えない（4 件在るはず）" % len(lang_bad)); ng += 1
    if [c for c in lang_bad if not c[3]]:
        print("  NG 決めていない訳の重複が残っている"); ng += 1
    else:
        print("  ok 訳の重複 %d 件すべてに正が決めてある" % len(lang_bad))
    # ⚠ 陽性: **決めた表を空にすると鳴る**こと（許しが効きすぎる壊れ方を見る）
    keep_l = dict(LANG_DECIDED)
    LANG_DECIDED.clear()
    left = [c for c in check_lang_collisions(sink0["entries"]) if not c[3]]
    LANG_DECIDED.update(keep_l)
    if left:
        print("  ok 陽性 決めた表を空にすると %d 件が「未決」に化ける" % len(left))
    else:
        print("  NG 陽性 空にしても鳴らない（許しが効きすぎている）"); ng += 1
    # ⚠ 陰性: 勝った名前空間からは落とさない／負けた側からは落とす
    key = next(iter(keep_l))
    win = keep_l[key][0]
    probe = json.dumps({key: "x", "other.key": "y"}).encode()
    _b, drop_w = apply_lang_decision("assets/%s/lang/ja_jp.json" % win, probe)
    _b2, drop_l = apply_lang_decision("assets/medievalorigins/lang/ja_jp.json", probe)
    if not drop_w and drop_l == [key]:
        print("  ok 陰性 勝った側は残し、負けた側からだけ落とす")
    else:
        print("  NG 陰性 落とし方が逆（勝ち側 %s ／ 負け側 %s）" % (drop_w, drop_l)); ng += 1

    # ⚠⚠ **合成の対照**（2026-09-01）。⚠ **段4で本当にぶつかるファイルで試す。**
    #    ⚠ 作り物ではなく、`origins_diet` と混ぜた jar の実物を使う——
    #    ⚠ **段4に入った瞬間これが起きる**ので、その前に効くことを見ておく。
    W3 = os.path.join(MC, "worlds", "world-3")
    dp_meat = os.path.join(W3, "datapacks", "origins_diet", "src", "data",
                           "origins", "tags", "items", "meat.json")
    jar_meat = None
    for stem in TOP:
        with zipfile.ZipFile(resolve(stem)) as z:
            try:
                jar_meat = z.read("data/origins/tags/items/meat.json")
                break
            except KeyError:
                continue
    if jar_meat is None or not os.path.isfile(dp_meat):
        print("  – 合成 試験の材料が無い（meat.json）")
    else:
        with io.open(dp_meat, "rb") as fh:
            dp_blob = fh.read()
        a = json.loads(jar_meat.decode("utf-8-sig")).get("values", [])
        b = json.loads(dp_blob.decode("utf-8-sig")).get("values", [])
        merged, _note = merge_tag([("jar", jar_meat), ("datapack", dp_blob)])
        got = json.loads(merged.decode("utf-8")).get("values", [])
        # ⚠ 陽性: 両方の値が残ること（＝1つ選ぶと消えていた分）
        miss_a = [v for v in a if v not in got]
        miss_b = [v for v in b if v not in got]
        if not miss_a and not miss_b and len(got) == len(a) + len(b):
            print("  ok 陽性 タグを合わせた（jar %d ＋ datapack %d → %d 件・欠け 0）"
                  % (len(a), len(b), len(got)))
        else:
            print("  NG 陽性 合わせ損ねた（jar から %d ／ datapack から %d 欠け・計 %d）"
                  % (len(miss_a), len(miss_b), len(got)))
            ng += 1
        # ⚠ 陰性: **1つ選ぶと本当に消える**ことを見る（合成が要る理由の対照）
        if len([v for v in a if v not in b]) > 0:
            print("  ok 陰性 1つ選ぶと %d 件が消えていた（合成が要る理由）"
                  % len([v for v in a if v not in b]))
        else:
            print("  NG 陰性 1つ選んでも消えない（材料が対照になっていない）")
            ng += 1
        # ⚠ 陽性: `replace:true` はそこまでを捨てること
        rep = json.dumps({"replace": True, "values": ["x:only"]}).encode()
        m2, _n2 = merge_tag([("jar", jar_meat), ("rep", rep)])
        if json.loads(m2.decode("utf-8"))["values"] == ["x:only"]:
            print("  ok 陽性 `replace:true` はそれより前を捨てる")
        else:
            print("  NG 陽性 `replace:true` が効いていない"); ng += 1

    # ⚠ 陽性: 訳は鍵ごとに合わさること（どちらか一方だけが持つ鍵も残る）
    la = json.dumps({"a": "1", "same": "old"}).encode()
    lb = json.dumps({"b": "2", "same": "new"}).encode()
    lm, _ln = merge_lang([("A", la), ("B", lb)])
    d = json.loads(lm.decode("utf-8"))
    if d == {"a": "1", "b": "2", "same": "new"}:
        print("  ok 陽性 訳を鍵ごとに合わせた（後の入力が勝つ／片方だけの鍵も残る）")
    else:
        print("  NG 陽性 訳の合成が違う: %s" % d); ng += 1

    # ⚠ 陰性: 選ぶべき種類には合成を当てないこと
    for p, want in (("data/origins/powers/light_armor.json", None),
                    ("data/origins/tags/items/meat.json", UNION_TAG),
                    ("assets/origins/lang/ja_jp.json", UNION_LANG)):
        got_kind = merge_kind_any(p)
        has = MERGERS.get(got_kind) is not None
        if (want is None and not has) or (want is not None and got_kind == want and has):
            print("  ok 種類の見分け %-46s → %s" % (p, got_kind))
        else:
            print("  NG 種類の見分け %s → %s" % (p, got_kind)); ng += 1

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
    # ⚠ `BUILT`（当部が建てた jar）を使わず、配布 jar だけで混ぜる。
    #   ⚠ 段1・段2 の「配っている jar と同じ物が出る」を確かめ直したいときに使う。
    a.add_argument("--released", action="store_true",
                   help="当部が建てた jar を使わず、配布 jar だけで混ぜる")
    # ⚠ 段4 の前後を比べるための口。⚠ **既定は入れる。**
    a.add_argument("--no-datapacks", action="store_true",
                   help="当部の datapack を jar へ入れない（段4 の前の形）")
    ns = a.parse_args(argv)
    if ns.released:
        global USE_BUILT
        USE_BUILT = False
        print("⚠ `--released`: 当部が建てた jar を使わない（配布 jar だけで混ぜる）")
    if ns.no_datapacks:
        global USE_DATAPACKS
        USE_DATAPACKS = False
        print("⚠ `--no-datapacks`: 当部の datapack を jar へ入れない（段4 の前の形）")
    return self_test() if ns.self_test else run(write=ns.write)


if __name__ == "__main__":
    sys.exit(main())
