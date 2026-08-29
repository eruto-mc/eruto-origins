> ## ⚠ これは当部の統合版です（eruto-mc / eruto-origins）
>
> 上流: [EdwinMindcraft/origins-forge](https://github.com/EdwinMindcraft/origins-forge)
> ／ 枝 `eruto/world3-1.20.1` ／ ライセンスは上流に従う（MIT）。
> **以下は上流の README です。**
>
> ### なぜ作ったか
>
> 第3ワールドの Origins まわりが **jar 8本・datapack 2つ・リソースパック・config** に
> 散っており、同じ id を2か所が別々に定義している件が5件（中身は5件とも違う）在った。
> ⚠ 上流の `origins-forge` は **2024-05-04 の 1.10.0.9 で止まっている**ので、
> 直すには当部がソースを持つしかない。設計は `minecraft-club` の
> `worlds/world-3/selection/design/origins-consolidation.md`。
>
> ### いまどこまで来ているか（段2まで済み）
>
> | 段 | やったこと | 判定 |
> | - | - | - |
> | **1** | 土台を ⚠ **配布された 1.10.0.9 の地点**（`67e2e0b`）に固定して建てた。⚠ **枝先はその2か月後で、jar になっていない修正が3件**入っているため（下記）。当部が入れた変更は AEA の取得先だけ（上流の `9dc15fe`。⚠ **元のホストが消えていてビルドが落ちる**。`build.gradle` の4行で、コードも版も変わらない） | `tools/compare_with_released.py` が **OK**（説明の付かない差 0。⚠ 違いはすべて javac の版で説明が付いた） |
> | **2** | ⚠⚠ **jar の中の class を差し替える手術をやめ、ソースから建てるようにした。** submodule `apoli` を当部の fork へ。`build.gradle` に MixinExtras を `compileOnly` で足した | 配っている `-eruto1` と突き合わせて **OK**。⚠ **差し替えていた5つの mixin のうち4つがバイト単位で一致** |
>
> ⚠ 段2で1つ見つけた: **パッチの理由を書いた注釈が、fork へ push したときに落ちていた**
> （当部が実際にビルドした写しには在った）。apoli 側で戻してある。
>
> ⚠ 当部の枝 `feat/wrapoperation-render-compat` には**上流の未リリース修正 #402 が混ざっていた**ので、
> **手術だけを取り出した枝 `eruto/world3-1.20.1`** を作ってそちらを指している。
>
> ### 上流の枝先に在る、jar になっていない修正3件
>
> ⚠ **段6（上流からの取り込み）で見る。いまは入れていない。**
>
> | 課題 | 題名 |
> | - | - |
> | [#454](https://github.com/EdwinMindcraft/origins-architectury/issues/454) | ⚠⚠ 以前に作ったワールドで種族の選択画面が出ない |
> | [#445](https://github.com/EdwinMindcraft/origins-architectury/issues/445) | 層の `gui_title` が効かない |
> | [#402](https://github.com/EdwinMindcraft/origins-architectury/issues/402) | ブロックに立ったときの耐性が正しく動かない |
>
> ### 建て方と確かめ方
>
> ```text
> JAVA_HOME=<17以上> ./gradlew build
> py -3.12 tools/compare_with_released.py
> ```
>
> ⚠ **`gradlew build` が通っただけでは足りない。** 必ず後者を回す——
> 配布された物との差を出し、**javac の版で説明が付く差だけか**を判定する
> （終了コード 0 が正）。⚠ **陰性対照も取ってある**: 当部のパッチ版 jar を
> `--built` に渡すと、差し替えた5つの mixin と refmap を名指しして落ちる。

# Origins (Forge)

This is the repository that is used to build Origins Forge.

## Building

To build this repository, first clone it, preferably with the `--recurse-submodules` flag.

Then run `gradlew build` in the root directory. The build output is the `unified` jar file.

## Creating addons

### 1.10.0.8 and above
Origins Forge is now hosted on the Ladysnake Maven. To use this, add the following to your gradle build script:
```gradle
repositories {
    ...
    maven {
        url "https://maven.ladysnake.org/releases"
    }
}

dependencies {
    ...
    implementation fg.deobf("io.github.edwinmindcraft:calio-forge:${calio_forge_version}")
    implementation fg.deobf("io.github.edwinmindcraft:apoli-forge:${apoli_forge_version}")
    implementation fg.deobf("io.github.edwinmindcraft:origins-forge:${origins_forge_version}")
}
```

You can find each individual version by looking at the [Reposilite maven page](https://maven.ladysnake.org/#/releases/io/github/edwinmindcraft).

Alternatively, you can look at the released JARs on the GitHub releases page of [EdwinMindcraft/origins-architectury](https://github.com/EdwinMindcraft/origins-architectury), just make sure to prefix the version with the Minecraft version as follows: `{minecraft_version}-{origins_forge_version}`.

### Older Versions
<details>
<summary>Expand</summary>

### 1.7.1.1-1.10.0.7

Origins Forge now uses the Greenhouse Maven to host its artifacts. To use this, add the following to your gradle build script:
```gradle
repositories {
    ...
    maven {
        url "https://maven.greenhouseteam.dev/releases"
    }
}

dependencies {
...
implementation fg.deobf("io.github.edwinmindcraft:calio-forge:${calio_forge_version}")
implementation fg.deobf("io.github.edwinmindcraft:apoli-forge:${apoli_forge_version}")
implementation fg.deobf("io.github.edwinmindcraft:origins-forge:${origins_forge_version}")
}
```

You can find each individual version by looking at the [Reposilite maven page](https://maven.merchantpug.net/#/releases/io/github/edwinmindcraft).

Alternatively, you can look at the released JARs on the GitHub releases page of [EdwinMindcraft/origins-architectury](https://github.com/EdwinMindcraft/origins-architectury), just make sure to prefix the version with the Minecraft version as follows: `{minecraft_version}-{origins_forge_version}`.

### Prior to 1.7.1.1
The simplest way to load Origins in a dev environment is currently to use
[Curse Maven](https://www.cursemaven.com/). To do so, add the flowing to your
gradle build script:
```gradle
repositories {
    ...
    maven {
        url "https://cursemaven.com"
        content {
            includeGroup "curse.maven"
        }
    }
}

dependencies {
    ...
    implementation fg.deobf("curse.maven:origins-474438:<fileid>")
}
```

You can find file ids on [CurseForge](https://www.curseforge.com/minecraft/mc-mods/origins-forge/files).
</details>


### Backup Mavens
Viable alternatives if one of these two methods don't work are the [Modrinth Maven](https://docs.modrinth.com/docs/tutorials/maven/) or [JitPack](https://jitpack.io/#EdwinMindcraft/origins-forge) (using a commit hash).

### Changes from fabric
Apoli for forge is partial rewrite of the fabric version, as such many compatiblity features
are currently missing. Furthermore, due to a mistake during the porting process, powers for
forge take Entities as argument instead of LivingEntities.

To register a power on forge, you'll need to use the regular forge process, either
with `RegistryEvent.Register` or `DeferredRegister`.

The registry types apoli forge uses are all defined in the package `io.github.edwinmindcraft.apoli.api.power.factory`.
If you want to use `DeferredRegister`, as classes are generics, consider using types
provided in `ApoliRegistries`.

While defining a power, action or condition the same way as fabric is possible,
if you are developing a pure forge addon, I would recommend using Mojang's `Codec`
system as well as `records` for static data storage as the system currently has builtin
support for error logging on those.

The system currently implemented is similar to the vanilla's Feature/ConfiguredFeature system, which
means most data will not change from one entity to another. If you do need to change data internally,
forge provides `ConfiguredPower.getPowerData` that will store any **mutable** data structure on the entity.

Other important changes:
* `ActionFactory` and `ConditionFactory` were split for each given subtype.
* When fabric used `Predicate` or `Consumer`, you'll need to use the matching `ConfiguredCondition` or `ConfiguredAction`
* Codecs are provided for most types, either in the class itself, or in the same places
as fabric `SerializableDataTypes` and `ApoliDataTypes`.
* Prefer using `CalioCodecHelper.optionalField` over `Codec.optionalFieldOf` 
  since those field will properly handle error logging.
* Prefer using `CalioCodecHelper.listOf` over `Codec.listOf` since those lists
  support the calio format of list.
* `SerializableDataTypes` can be used as `Codecs` of the same type.
* `SerializableData` can be used a `MapCodecs` of the same type.
* `PowerFactories` can by default be conditioned.

### Defining a new content

To define a new power, action or condition, you'll need a configuration which
implements `IDynamicFeatureConfiguration`. While this class doesn't have any
abstract methods, you can still override the methods provided to display additional
information in the logs for people defining datapacks using your content.