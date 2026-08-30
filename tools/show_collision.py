# -*- coding: utf-8 -*-
"""ぶつかっている data のパスについて、**持ち主全員の中身を並べる**。

⚠⚠ **なぜ要るか**: `check_merge_hazards.py` は「同じ名前が2つ以上ある」までしか言わない。
⚠ **その先（何が壊れるか・どれを残すか）は実物を開かないと決まらない**——
2026-08-30 に、開かずに結論を書いて外した（`data/origins/origin_layers/origin.json`）。

⚠ **開く先は jar だけではない。** 当部の datapack が同じパスを持っていることがあり、
⚠⚠ **そちらが `loading_priority` で勝っている**場合がある。この道具は両方を並べる。

    py -3.12 tools/show_collision.py data/origins/powers/light_armor.json

⚠ 出るもの: 持ち主ごとの中身と `loading_priority`、そして
⚠ **「上流と同じ内容の写しが在るか」**（在れば、その写しは消せる）。
"""
import json
import os
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MC = r"c:\@projects\minecraft-club"
MODS = os.path.join(MC, "worlds", "world-3", "dev", "instance", "mods")
DATAPACKS = os.path.join(MC, "worlds", "world-3", "datapacks")


def from_jars(path):
    """`mods/` の jar のうち、そのパスを持っているものを全部返す。"""
    out = []
    for name in sorted(os.listdir(MODS)):
        if not name.endswith(".jar"):
            continue
        try:
            with zipfile.ZipFile(os.path.join(MODS, name)) as zf:
                if path in zf.namelist():
                    out.append((name, zf.read(path).decode("utf-8", "replace")))
        except Exception:
            continue
    return out


def from_datapacks(path):
    """当部の datapack の `src/` のうち、そのパスを持っているものを全部返す。"""
    out = []
    if not os.path.isdir(DATAPACKS):
        return out
    for name in sorted(os.listdir(DATAPACKS)):
        f = os.path.join(DATAPACKS, name, "src", path.replace("/", os.sep))
        if os.path.isfile(f):
            with open(f, encoding="utf-8", errors="replace") as fh:
                out.append(("datapack:" + name, fh.read()))
    return out


def brief(text):
    try:
        d = json.loads(text)
    except Exception:
        return None, "（JSON として読めない）"
    lp = d.get("loading_priority", 0)
    keys = [k for k in d if not k.startswith("_")]
    return d, "loading_priority=%s ／ 鍵 %d 個: %s" % (lp, len(keys), ", ".join(sorted(keys))[:120])


def main():
    if len(sys.argv) < 2:
        raise SystemExit("使い方: show_collision.py <data/... のパス>")
    path = sys.argv[1].replace("\\", "/")

    owners = from_jars(path) + from_datapacks(path)
    print("パス: %s" % path)
    print("持ち主: %d" % len(owners))
    print()
    if not owners:
        return 1

    parsed = {}
    for name, text in owners:
        d, line = brief(text)
        parsed[name] = d
        print("########## %s" % name)
        print("    %s" % line)
        print(text.strip()[:900])
        print()

    # ⚠⚠ **どれが「上流」かを道具が推測しない**（2026-08-30 に `-eruto` を除外して
    #    空になった。当部がパッチした jar も、このパスについては上流の中身を持っている）。
    #    ⚠ **全部の組を突き合わせて、同じ中身のものを名指しするだけにする。**
    #    ⚠ どれを残すかは人が決める——ただし「同じ中身が2つある」なら**片方は消せる**。
    print("=== 中身が同じ組（⚠ 表示のための鍵と loading_priority を除いて比べる） ===")

    def core(d):
        if d is None:
            return None
        return {k: v for k, v in d.items()
                if k not in ("loading_priority", "name", "description", "hidden")
                and not k.startswith("_")}

    names = list(parsed)
    same = 0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ca, cb = core(parsed[a]), core(parsed[b])
            if ca is not None and ca == cb:
                same += 1
                print("  ⚠⚠ **%s** と **%s** は中身が同じ" % (a, b))
                pa = (parsed[a] or {}).get("loading_priority", 0)
                pb = (parsed[b] or {}).get("loading_priority", 0)
                print("      loading_priority: %s ／ %s → ⚠ **大きいほうが勝つ**"
                      "。⚠ **負けるほうは消せる**" % (pa, pb))
    if not same:
        print("  （同じ中身の組は無い。⚠ **全部が別物なので、1つを選ぶ判断が要る**）")
    print()
    print("⚠ **表示のための鍵の違いは別に見る**（name / description / hidden）:")
    for name, d in parsed.items():
        if d is None:
            continue
        shown = {k: d[k] for k in ("name", "description", "hidden") if k in d}
        print("  %-42s %s" % (name, json.dumps(shown, ensure_ascii=False) if shown else "（無し）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
