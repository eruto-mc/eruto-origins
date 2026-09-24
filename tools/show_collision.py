# -*- coding: utf-8 -*-
"""ぶつかっている data のパスについて、**持ち主全員の中身を並べる**。

⚠⚠ **なぜ要るか**: `build_bundle.py` は「決めていないぶつかり」で止まるとき、
パスと持ち主の名前までしか言わない。⚠ **その先（何が壊れるか・どれを残すか）は
実物を開かないと決まらない**——2026-08-30 に、開かずに結論を書いて外した
（`data/origins/origin_layers/origin.json`）。

⚠⚠ **読む材料は `build_bundle.py` と同じ**（2026-09-25 に向け直した）。
それまでは `instance/mods` の jar と古い置き場の datapack を見ていたので、
⚠ 1本に混ぜた後（2026-09-01〜）は**混ぜた jar しか見えず、上流の持ち主を並べられなかった**。
⚠ 上流の中身は、当部の分で差し替える**前**（`build_bundle.gather_upstream()`）から取る。

    py -3.12 tools/show_collision.py data/origins/powers/light_armor.json

⚠ 出るもの: 持ち主ごとの中身と、⚠ **中身が同じ組**（当部の分が上流と同じ中身なら、当部の分は要らない）。
⚠ どれが勝つかは `build_bundle.py` の決まりどおり: ⚠ **当部の分（`datapack:`）が在れば、それが勝つ**
（足し合わせる種類＝タグ・訳・層は合わせる）。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_bundle as BB  # noqa: E402  ⚠ 材料の探し方はあちらが正


def owners_of(path):
    """そのパスの持ち主を (名前, 中身) で全部返す。上流（7本と溶かす土台）→ 当部の分 の順。"""
    sink = BB.gather_upstream()[0]
    out = [(label, blob.decode("utf-8", "replace"))
           for label, blob in sink["entries"].get(path, [])]
    for label, rel, blob in BB.datapack_entries():
        if rel == path:
            out.append((label, blob.decode("utf-8", "replace")))
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

    owners = owners_of(path)
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
    #    ⚠ どれを残すかは人が決める——ただし当部の分が上流と同じ中身なら**当部の分は要らない**。
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
                if a.startswith("datapack:") or b.startswith("datapack:"):
                    print("      ⚠ **当部の分が上流と同じ中身なので、当部の分は要らない**"
                          "（消しても混ぜた jar の中身は変わらない）")
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
