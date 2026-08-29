# -*- coding: utf-8 -*-
"""jar を1本にまとめるときに**黙って壊れる**所を、まとめる前に数える。

⚠⚠ **なぜ要るか**: 別々の jar に在るときは共存できるのに、
1つにまとめた瞬間に**同じ名前のファイルが1つしか残らない**ものがある。
⚠ **上書きされたほうは、エラーを出さずに機能だけ消える。**

見るもの:

  ① `META-INF/services/*`        … ServiceLoader の登録。⚠ **同名なら片方が消える**
  ② `*.mixins.json` / refmap     … ⚠ 別セッションが 2026-08-30 に踏んだ所
  ③ `pack.mcmeta`                … 1つしか置けない
  ④ `META-INF/MANIFEST.MF` の鍵  … `MixinConfigs` は**全部を並べないと読まれない**
  ⑤ 同じ `data/` `assets/` のパス … 片方が消える

    py -3.12 tools/check_merge_hazards.py

⚠⚠ **この道具が言えるのは「同じ名前が2つ以上ある」までである。**

⚠ **その先（何が壊れるか）は、実物を開いて人が書くこと。**
2026-08-30 に、この出力を見て「MOR の19種族が層から丸ごと落ちる」と書いたが**誤りだった**——
⚠ **当部の datapack が同じパスを `replace: true` で置き換えており、
MOR の層ファイルは今日すでに読まれていなかった**（ファイルを開かずに結末を書いていた）。

⚠ **ぶつかった1件ごとに、少なくとも次を開いてから結論を書く:**

  ・両方のファイルの中身（`unzip -p <jar> <パス>`）
  ・当部の datapack が同じパスを持っていないか（持っていれば、そちらが勝つことがある）
  ・その形式の合成の規則（Origins の層なら `replace`）
"""
import collections
import os
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODS = (r"c:\@projects\minecraft-club\worlds\world-3\dev\clones"
        r"\mor-siphon\mods")
# ⚠ 段3〜4 で1本にまとめる予定のもの（Pehkui は外に残すので入れない）
TARGETS = [
    "origins-forge-1.20.1-1.10.0.9-all-eruto1.jar",
    "origins-classes-forge-1.2.1.jar",
    "Medieval Origins Revival-6.6.0+1.20.1-forge-eruto1.jar",
    "origins_umbrellas-1.6.1-eruto1.jar",
    "solapplepie_origins_fix-1.0.0.jar",
    "shifting_origins-1.9.1.jar",
    "orb_layer_variants-1.1.0.jar",
]


def entries(path):
    """入れ子の jar は**中身も**数える（JarJar の分が本体のことがある）。"""
    out = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            out[name] = None
    return out


def manifest_keys(path):
    try:
        with zipfile.ZipFile(path) as zf:
            if "META-INF/MANIFEST.MF" not in zf.namelist():
                return {}
            text = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except Exception:
        return {}
    keys = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            keys[k.strip()] = v.strip()
    return keys


def main():
    present = [t for t in TARGETS if os.path.exists(os.path.join(MODS, t))]
    missing = [t for t in TARGETS if t not in present]
    print("まとめる予定: %d 本（見つかった %d ／ 無い %d）"
          % (len(TARGETS), len(present), len(missing)))
    for m in missing:
        print("  ⚠ 見つからない: %s" % m)
    print()

    owners = collections.defaultdict(list)
    for name in present:
        for entry in entries(os.path.join(MODS, name)):
            owners[entry].append(name)

    def report(title, pred, show_all=False):
        hits = {k: v for k, v in owners.items() if pred(k)}
        clash = {k: v for k, v in hits.items() if len(v) > 1}
        print("### %s — 全 %d 件／⚠ **ぶつかる %d 件**" % (title, len(hits), len(clash)))
        for k in sorted(clash):
            print("  ⚠⚠ %s" % k)
            for o in clash[k]:
                print("        %s" % o)
        if show_all and not clash:
            for k in sorted(hits):
                print("     %s  ← %s" % (k, hits[k][0]))
        print()
        return len(clash)

    bad = 0
    bad += report("① META-INF/services",
                  lambda k: k.startswith("META-INF/services/"), show_all=True)
    bad += report("② mixin の設定と refmap",
                  lambda k: k.endswith(".mixins.json") or k.endswith("refmap.json"),
                  show_all=True)
    bad += report("③ pack.mcmeta / mods.toml",
                  lambda k: k in ("pack.mcmeta", "META-INF/mods.toml"))
    bad += report("⑤ data / assets の同じパス",
                  lambda k: k.startswith("data/") or k.startswith("assets/"))

    print("### ④ MANIFEST の鍵（⚠ **まとめると1つしか残らない**）")
    for name in present:
        keys = manifest_keys(os.path.join(MODS, name))
        interesting = {k: v for k, v in keys.items()
                       if k in ("MixinConfigs", "FMLModType", "Automatic-Module-Name",
                                "Implementation-Title")}
        if interesting:
            print("  %s" % name)
            for k, v in sorted(interesting.items()):
                print("      %-22s %s" % (k, v))
    print()
    print("⚠ ぶつかる合計: %d 件" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
