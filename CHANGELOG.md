# Origins
- Fixed Origin registry sometimes not containing any values other than `origins:empty` on the client. [#423](https://github.com/EdwinMindcraft/origins-architectury/issues/423)
# Apoli
- Fixed potential null return values for `status_bar_texture` powers.
- Fixed `prevent_sprinting` power not functioning. [#427](https://github.com/EdwinMindcraft/origins-architectury/issues/427)
- Fixed `min_duration` field default not accounting for infinite effect durations in `status_effect` condition. [#438](https://github.com/EdwinMindcraft/origins-architectury/issues/438) 
- Fixed `exposed_to_sky` and `exposed_to_sun` not having the correct block position within negative x and z coordinates. [#439](https://github.com/EdwinMindcraft/origins-architectury/issues/439)
# Calio
- Fixed registries sometimes not containing any values other than the default on the client. [#423](https://github.com/EdwinMindcraft/origins-architectury/issues/423)
- Consistent-ify isServerContext with older version fixes.

# For Addon Devs:
### Origins Forge is now hosted on the Ladysnake Maven
The notation for the artifacts are still the exact same, but you will have to replace the MerchantPug maven with the Ladysnake maven within your `repositories` block. This is the same repository as Origins Fabric.
```diff
repositories {
    ...
+   maven {
+       url "https://maven.ladysnake.org/releases"
+   }
-   maven {
-       url "https://maven.merchantpug.net/releases"
-   }
}
```
### Apoli
- The PowerType class is no longer abstract, meaning you can instantiate it directly.