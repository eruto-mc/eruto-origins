# -*- coding: utf-8 -*-
"""混ぜる**前の 7 本**と、混ぜた**後の 1 本**が、同じことを名乗っているかを突き合わせる。

  py -3.12 tools/check_bundle_parity.py
  py -3.12 tools/check_bundle_parity.py --detail
  py -3.12 tools/check_bundle_parity.py --self-test

終了コード: 0 = 説明の付かない差が無い ／ 1 = 在る

## ⚠⚠ なぜ要るか（2026-09-01 制定）

⚠ 混ぜる作業で実機が 3 回落ちたが、⚠⚠ **3 回とも「大声で失敗する」型**だった:

| 落ちた原因 | 型 |
| - | - |
| package の衝突（`mixinextras`） | 起動前に落ちる |
| `modLoader` の違い（`solapplepie_origins_fix`） | 起動前に落ちる |
| AutoModpack の配り先の漏れ（`orb_layer_variants` が二重） | 部員が入れない |

⚠ そして `build_bundle.py` に足した検査（`check_mergeable` / `check_packages` /
`NEST_AS_IS`）も**全部その型**。⚠⚠ **「起動して、動いて、値だけが違う」型の検査が 1 つも無かった。**

⚠ 実例（この道具が最初に捕まえたもの）: ⚠⚠ **`originsumbrellas` と `shiftingorigins` の
版が `0.0NONE` になっていた。** 遊び用サーバは何事も無く動き、ログの 1 行だけが違った。

  * この 2 本だけが `mods.toml` に `version="${file.jarVersion}"` と書いている
  * Forge はそれを jar の MANIFEST の `Implementation-Version` から採る
    （`fmlloader` の `net/minecraftforge/fml/loading/moddiscovery/ModFile.class` に
    `jarVersion` と `0.0NONE` の両方の文字列が在る）
  * ⚠ ところが `build_bundle.py` の書く MANIFEST は 2 行しかない
    （`Manifest-Version` と `MixinConfigs`）。⚠ **元の 7 本は全部 `Implementation-Version` を持っていた**

## 見るもの（4 つ。どれも「落ちた物を名指しする」）

  ① modId と版      … 7 本を読んだときと、1 本を読んだときで同じか
  ② MANIFEST の欄   … 元が持っていた欄のうち、捨てた物を名指しする
  ③ data / assets   … 入り口が 1 つでも落ちていないか（増えた分も出す）
  ④ mixin の設定    … 元の `*.mixins.json` が全部登録されているか
                       （MANIFEST の `MixinConfigs` か `[[mods]]` 側の `[[mixins]]`）

## ⚠ この道具が見ないもの（**わざと**）

⚠⚠ **値の中身は見ない。** タグ・層・lang は「同じパスが在る」だけでは足りず、
⚠ **値の集合で突き合わせないと嘘になる**（`replace:false` のタグは足し合わせなので、
1 つに畳むと片方の値が黙って消える）。⚠ **そちらは段 4 の合成と同じ知識**なので、
⚠ **合成を書くときに一緒に書く**——ここに先に書くと、種類ごとの規則の表が 2 か所になる。

⚠ 一覧は `build_bundle.py` から読む（**写さない**）。
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
sys.path.insert(0, HERE)

import build_bundle as BB          # noqa: E402  ⚠ 一覧はこちらが正

# ⚠⚠ **名前を決め打ちしない**（2026-09-01）。⚠ 版が「日付＋入力の指紋」になったので、
#    ⚠ 書けば必ず腐る。⚠ **作る側（`build_bundle`）が名前を決め、こちらは聞く。**
BUNDLE = os.path.join(BB.OUT_DIR, BB.bundle_name())

# ⚠ `build_bundle.py` が**作り直す**入り口。落ちていても誤りではない。
REWRITTEN = {
    "META-INF/mods.toml",
    "META-INF/MANIFEST.MF",
    "META-INF/accesstransformer.cfg",
    "META-INF/coremods.json",
    "pack.mcmeta",
}

# ⚠ 混ぜた jar にだけ在ってよい物（作る側が足す）。
ADDED_OK = ("META-INF/jarjar/", "LICENSES.md")

# ⚠⚠ **捨ててよい MANIFEST の欄と、その理由。**
#
# ⚠ **既定は「捨てたら鳴る」。** ここに書いた分だけ鳴らさない。
# ⚠ 逆（「この欄だけ見る」の一覧）にすると、⚠⚠ **新しく効く欄が増えたとき静かに素通りする。**
# ⚠ 鳴りすぎるほうは気づけるが、黙って消える欄には誰も気づけない。
#
# ⚠ 理由は**1 行で完結させる**（「同上」と書かない）。
#   ⚠ この表は名前順に並べて印字するので、⚠⚠ **書いた順の「上」は印字の「上」ではない。**
MANIFEST_DROP_OK = {
    "Specification-Title": "画面に出す名前だけ。1 本にすると 1 つしか書けない",
    "Specification-Vendor": "画面に出す作者名だけ。1 本にすると 1 つしか書けない",
    "Specification-Version": "画面に出す版だけ。本当の版は `[[mods]]` の `version` に在る",
    "Implementation-Title": "画面に出す名前だけ。1 本にすると 1 つしか書けない",
    "Implementation-Vendor": "画面に出す作者名だけ。1 本にすると 1 つしか書けない",
    "Implementation-Timestamp": "建てた時刻。混ぜた物には意味が無い",
    "Built-On-Java": "MOR が自分で足している覚え書き。Forge は読まない",
    "Build-On-Minecraft": "MOR が自分で足している覚え書き。Forge は読まない",
    "Timestampe": "MOR の綴り違い（上流のまま）。誰も読まない",
    "MixinConfigs": "作り直している。④ で登録を数える",
}

# ⚠⚠ **`Implementation-Version` だけは条件つき。**
#    ⚠ Forge は `${file.jarVersion}` をこの欄から採るので、
#    ⚠ **`mods.toml` にその書き方が 1 つでも残っていたら、捨ててはいけない。**
#    ⚠ 残っていなければ、解決する物が無いので捨ててよい。
COND_FIELD = "Implementation-Version"


def read_jar(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def manifest_keys(blob):
    """MANIFEST の主区画の欄名を採る（続き行は無視する）。"""
    t = blob.decode("utf-8", "replace")
    out = {}
    for line in t.replace("\r\n", "\n").split("\n"):
        if not line or line.startswith(" "):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def mods_of(entries):
    """`mods.toml` から (modId, 版の書き方) を採り、`${file.jarVersion}` を解く。

    ⚠ Forge は `${file.jarVersion}` を MANIFEST の `Implementation-Version` から採る。
    ⚠ **無ければ `NONE` になる**（この道具が最初に捕まえたのがそれ）。
    """
    toml = entries.get("META-INF/mods.toml")
    if toml is None:
        return []
    t = toml.decode("utf-8", "replace")
    mf = manifest_keys(entries.get("META-INF/MANIFEST.MF", b""))
    impl = mf.get("Implementation-Version")

    out, cur, inmods = [], {}, False
    for line in t.splitlines():
        s = re.sub(r"#.*$", "", line).strip()
        if s.startswith("[["):
            if inmods and cur.get("modId"):
                out.append(cur)
            cur, inmods = {}, (s == "[[mods]]")
            continue
        if s.startswith("["):
            if inmods and cur.get("modId"):
                out.append(cur)
            cur, inmods = {}, False
            continue
        if not inmods:
            continue
        m = re.match(r'modId\s*=\s*["\']([^"\']+)', s)
        if m:
            cur["modId"] = m.group(1)
        m = re.match(r'version\s*=\s*["\']([^"\']*)', s)
        if m:
            cur["raw"] = m.group(1)
    if inmods and cur.get("modId"):
        out.append(cur)

    for c in out:
        raw = c.get("raw", "")
        if "${file.jarVersion}" in raw:
            c["resolved"] = (raw.replace("${file.jarVersion}", impl)
                             if impl else "⚠ 解決できない（NONE になる）")
            c["needs_manifest"] = True
        else:
            c["resolved"] = raw
            c["needs_manifest"] = False
    return out


def mixin_configs(entries):
    """その jar が持っている、根の `*.mixins.json` の名前。"""
    return {n for n in entries if n.endswith(".mixins.json") and "/" not in n}


def registered_configs(entries):
    """混ぜた jar が**登録している**設定名（MANIFEST と `[[mixins]]` の両方）。"""
    got = set()
    mf = manifest_keys(entries.get("META-INF/MANIFEST.MF", b""))
    for s in (mf.get("MixinConfigs") or "").split(","):
        if s.strip():
            got.add(s.strip())
    toml = entries.get("META-INF/mods.toml", b"").decode("utf-8", "replace")
    for m in re.finditer(r'config\s*=\s*["\']([^"\']+)', toml):
        got.add(m.group(1))
    return got


def gather_inputs():
    """混ぜる前の入力を読む。返り値: {見出し: {入り口: 中身}}。

    ⚠⚠ **段4 から、当部の datapack も入力**（2026-09-01）。
    ⚠ 教えないと **238 件が「増えた」に見える**——⚠ **検査が作る側に追いついていない**だけで、
    ⚠ そこを黙って通すと、⚠⚠ **本当に増えた物も見えなくなる。**
    """
    src = {}
    for stem in BB.TOP:
        p = BB.resolve(stem)
        src[os.path.basename(p)] = read_jar(p)
    for label, rel, blob in BB.datapack_entries():
        src.setdefault(label, {})[rel] = blob
    return src


def run(detail=False, bundle_path=None, src=None):
    path = bundle_path or BUNDLE
    if not os.path.isfile(path):
        print("!! 混ぜた jar が無い: %s" % path)
        print("⚠ 先に `py -3.12 tools/build_bundle.py --write` を回す。")
        return 1
    if src is None:
        src = gather_inputs()
    out = read_jar(path)
    drop = BB.mor_drop()
    ng = []

    # ---------------- ① modId と版 ----------------
    print("== ① modId と版 ==")
    want = {}
    for name, ent in sorted(src.items()):
        for c in mods_of(ent):
            want[c["modId"]] = (c["resolved"], name, c["needs_manifest"])
    got = {c["modId"]: c["resolved"] for c in mods_of(out)}

    for mid in sorted(want):
        w, src_name, needs = want[mid]
        g = got.get(mid)
        if g is None:
            print("   !! %-22s 混ぜた jar に居ない（元: %s）" % (mid, src_name))
            ng.append("modId %s が落ちた" % mid)
        elif g != w:
            print("   !! %-22s 元 `%s` → 混ぜた後 `%s`%s"
                  % (mid, w, g, "  ⚠ `${file.jarVersion}` を使う MOD" if needs else ""))
            ng.append("%s の版が変わった（%s → %s）" % (mid, w, g))
        elif detail:
            print("   ok %-22s %s" % (mid, g))
    extra_ids = sorted(set(got) - set(want))
    for mid in extra_ids:
        print("   !! %-22s 元の 7 本に居ない modId が増えた" % mid)
        ng.append("modId %s が増えた" % mid)
    print("   元 %d 個 ／ 混ぜた後 %d 個" % (len(want), len(got)))

    # ---------------- ② MANIFEST の欄 ----------------
    print("== ② MANIFEST の欄 ==")
    keep = manifest_keys(out.get("META-INF/MANIFEST.MF", b""))
    lost = {}
    for name, ent in sorted(src.items()):
        for k, v in manifest_keys(ent.get("META-INF/MANIFEST.MF", b"")).items():
            if k not in keep:
                lost.setdefault(k, []).append("%s=%s" % (name, v))
    # ⚠ `${file.jarVersion}` が混ぜた `mods.toml` に残っているか（条件つきの欄のため）
    out_toml = out.get("META-INF/mods.toml", b"").decode("utf-8", "replace")
    placeholder_left = "${file.jarVersion}" in out_toml

    for k in sorted(lost):
        why = MANIFEST_DROP_OK.get(k)
        if k == COND_FIELD:
            why = (None if placeholder_left
                   else "混ぜた `mods.toml` に `${file.jarVersion}` が残っていない"
                        "ので、解決する物が無い")
        bad_field = why is None
        print("   %s %-28s 捨てた（元: %s）"
              % ("!!" if bad_field else "  ", k, "／".join(lost[k][:3])))
        print("        %s" % (why or "⚠⚠ **理由が書いていない。**"
                                     "捨ててよいなら `MANIFEST_DROP_OK` に理由つきで書く"))
        if bad_field:
            ng.append("MANIFEST の %s を捨てた" % k)
    if not lost:
        print("   ok 捨てた欄は無い")
    print("   混ぜた jar が持つ欄: %s" % ", ".join(sorted(keep)))
    print("   ⚠ 混ぜた `mods.toml` に `${file.jarVersion}` が %s"
          % ("残っている（＝ `Implementation-Version` が要る）" if placeholder_left
             else "残っていない"))

    # ---------------- ③ data / assets の入り口 ----------------
    print("== ③ data / assets の入り口 ==")
    want_e = set()
    for name, ent in src.items():
        for n in ent:
            if n.startswith("META-INF/jarjar/") or n in REWRITTEN or n in drop:
                continue
            want_e.add(n)
    missing = sorted(want_e - set(out))
    extra = sorted(n for n in set(out) - want_e - REWRITTEN
                   if not n.startswith(ADDED_OK))
    print("   元の入り口 %d ／ 混ぜた後 %d ／ ⚠ 落ちた %d ／ 増えた %d"
          % (len(want_e), len(out), len(missing), len(extra)))
    for n in missing[:30]:
        owners = [s for s, e in src.items() if n in e]
        print("   !! 落ちた %-56s ← %s" % (n, "／".join(owners)))
    if len(missing) > 30:
        print("   … 他 %d 件" % (len(missing) - 30))
    for n in extra[:15]:
        print("   !! 増えた %s" % n)
    if missing:
        ng.append("入り口が %d 件落ちた" % len(missing))
    if extra:
        ng.append("入り口が %d 件増えた" % len(extra))
    print("   ⚠ MOR から抜いた %d 件は落ちてよい分として数えていない" % len(drop))

    # ---------------- ④ mixin の設定 ----------------
    print("== ④ mixin の設定 ==")
    want_c = set()
    for ent in src.values():
        want_c |= mixin_configs(ent)
    reg = registered_configs(out)
    for c in sorted(want_c):
        if c not in reg:
            print("   !! %-40s 登録されていない（ログに 1 行も出ずに死ぬ）" % c)
            ng.append("mixin の設定 %s が未登録" % c)
        elif c not in out:
            print("   !! %-40s 登録は在るが、中身が jar に無い" % c)
            ng.append("mixin の設定 %s の実体が無い" % c)
        elif detail:
            print("   ok %s" % c)
    print("   元の設定 %d 本 ／ 登録されている %d 本" % (len(want_c), len(reg)))

    print()
    if ng:
        print("== ⚠⚠ 説明の付かない差 %d 件 ==" % len(ng))
        for s in ng:
            print("   !! %s" % s)
        return 1
    print("OK 説明の付かない差は無い")
    return 0


def _rebuild(entries):
    """辞書から zip を組み直す（自己試験用・記憶の中だけ）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in entries.items():
            z.writestr(n, b)
    buf.seek(0)
    return buf


def _break_toml(out_toml, src):
    """⚠ **自己試験の中だけで使う。** 版を `${file.jarVersion}` に戻した toml を作る。

    ⚠⚠ **なぜ要るか**: 陽性対照が「いまの jar が壊れていること」に寄りかかっていると、
    ⚠ **直した瞬間に試験そのものが壊れる**（実際に 2026-09-01 に壊れた）。
    ⚠ **壊れた形は、その場で作る。**
    """
    impl = {name: manifest_keys(ent.get("META-INF/MANIFEST.MF", b""))
            .get("Implementation-Version")
            for name, ent in src.items()}
    out, cur = [], None
    for line in out_toml.splitlines():
        m = re.match(r"^#\s*----\s*(.+?)\s*----\s*$", line)
        if m:
            cur = impl.get(m.group(1))
        if cur and re.match(r'\s*version\s*=\s*["\']%s["\']' % re.escape(cur), line):
            line = re.sub(re.escape(cur), "${file.jarVersion}", line)
        out.append(line)
    return "\n".join(out) + "\n"


def _repair_toml(out_toml, src):
    """⚠ **自己試験の中だけで使う。** `${file.jarVersion}` を元の版で埋めた toml を作る。

    ⚠ `build_bundle.py` が書く toml は `# ---- <jar名> ----` で区切ってあるので、
    ⚠ **その区切りごとに、その jar の `Implementation-Version` を当てる。**

    ⚠⚠ **直す側の実装をここに置かない**（置くと作る側と 2 か所になる）。
    ⚠ ここは「直ったらどうなるか」を試験で作るためだけのもの。
    """
    impl = {name: manifest_keys(ent.get("META-INF/MANIFEST.MF", b""))
            .get("Implementation-Version")
            for name, ent in src.items()}
    out, cur = [], None
    for line in out_toml.splitlines():
        m = re.match(r"^#\s*----\s*(.+?)\s*----\s*$", line)
        if m:
            cur = impl.get(m.group(1))
        if cur and "${file.jarVersion}" in line:
            line = line.replace("${file.jarVersion}", cur)
        out.append(line)
    return "\n".join(out) + "\n"


def self_test():
    """⚠ **直した形を先に作って 0 になることを見てから**、1 つずつ壊して鳴ることを見る。

    ⚠⚠ **いまの混ぜた jar は既に NG なので、「壊したら鳴った」は何も証明しない**
    （壊す前から鳴っている）。⚠ だから**陰性対照（直した形が 0 になる）を先に置く。**
    """
    print("== 自己試験 ==")
    ng = 0
    src = gather_inputs()
    base = read_jar(BUNDLE) if os.path.isfile(BUNDLE) else None
    if base is None:
        print("  NG 混ぜた jar が無いので試験できない")
        return 1

    tmp = os.path.join(BB.OUT_DIR, "_parity_selftest.jar")

    def check_with(entries, label, expect_ng):
        with open(tmp, "wb") as fh:
            fh.write(_rebuild(entries).read())
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            rc = run(bundle_path=tmp, src=src)
        finally:
            sys.stdout = old
        ok = (rc != 0) if expect_ng else (rc == 0)
        print("  %s %s（終了コード %d）" % ("ok" if ok else "NG", label, rc))
        if not ok:
            for l in buf.getvalue().splitlines():
                if "!!" in l:
                    print("       %s" % l.strip())
        return 0 if ok else 1

    # ⚠⚠ **まず陰性対照**: いまの誤り（`${file.jarVersion}` が解けない）だけを直した形が
    #    0 になること。⚠ **これが 0 にならないなら、この道具の判定が壊れている。**
    fixed = dict(base)
    fixed["META-INF/mods.toml"] = _repair_toml(
        base["META-INF/mods.toml"].decode("utf-8", "replace"), src).encode("utf-8")
    ng += check_with(fixed, "陰性 版を埋めた形は 0 になる", expect_ng=False)

    # ⚠ 以下は**直した形から**1 つずつ壊す。
    # ⚠⚠ **いまの jar は既に NG なので、そこから壊しても何も証明しない。**

    # ⚠ 陽性1: 版を `${file.jarVersion}` へ戻す（＝ 2026-09-01 に実機で起きた形）
    # ⚠⚠ **`base` に寄りかからない。** ⚠ 直すと `base` は壊れていないので、
    #    ⚠ 「いまの状態」を陽性対照に使うと**直した日に試験が壊れる**（実際に壊れた）。
    e = dict(fixed)
    e["META-INF/mods.toml"] = _break_toml(
        fixed["META-INF/mods.toml"].decode("utf-8", "replace"), src).encode("utf-8")
    ng += check_with(e, "陽性 版を埋めないと鳴る（0.0NONE の形）", expect_ng=True)

    # ⚠ 陽性2: data の入り口を 1 つ落とす
    e = dict(fixed)
    victim = next(n for n in sorted(e) if n.startswith("data/") and n.endswith(".json"))
    del e[victim]
    ng += check_with(e, "陽性 入り口を 1 つ消すと鳴る（%s）" % victim, expect_ng=True)

    # ⚠ 陽性3: mixin の設定を MANIFEST から 1 つ外す
    e = dict(fixed)
    mf = e["META-INF/MANIFEST.MF"].decode("utf-8", "replace")
    e["META-INF/MANIFEST.MF"] = re.sub(r"origins\.mixins\.json,", "", mf).encode()
    ng += check_with(e, "陽性 設定を 1 つ外すと鳴る", expect_ng=True)

    # ⚠ 陽性4: modId を 1 つ消す
    e = dict(fixed)
    t = e["META-INF/mods.toml"].decode("utf-8", "replace")
    e["META-INF/mods.toml"] = t.replace('modId="shiftingorigins"',
                                        'modId="zzz_gone"').encode()
    ng += check_with(e, "陽性 modId を変えると鳴る", expect_ng=True)

    # ⚠⚠ 陽性5: **許し一覧が効きすぎる壊れ方を見る。**
    #    ⚠ `MANIFEST_DROP_OK` を空にすると、捨てている欄が全部「理由なし」に化けるはず。
    keep_ok = dict(MANIFEST_DROP_OK)
    MANIFEST_DROP_OK.clear()
    rc5 = check_with(fixed, "陽性 許し一覧を空にすると鳴る", expect_ng=True)
    MANIFEST_DROP_OK.update(keep_ok)
    ng += rc5

    try:
        os.remove(tmp)
    except OSError:
        pass
    print("判定: NG %d 件" % ng)
    return 1 if ng else 0


def main(argv=None):
    a = argparse.ArgumentParser()
    a.add_argument("--detail", action="store_true")
    a.add_argument("--self-test", action="store_true")
    ns = a.parse_args(argv)
    return self_test() if ns.self_test else run(detail=ns.detail)


if __name__ == "__main__":
    sys.exit(main())
