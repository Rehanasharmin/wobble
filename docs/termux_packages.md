# Verified Termux packages and install commands

Wobble prints install commands from one source of truth:
[`wobble/core/packages.py`](../wobble/core/packages.py). This page records what
was verified, against which upstream source, and which package names are **not**
real — so the next edit does not reintroduce a command that cannot work.

Verified on **23 October 2026** against
[`termux/termux-packages`](https://github.com/termux/termux-packages) (`master`)
and the Termux wiki. Termux package names change rarely, but always confirm with
`pkg search <name>` on the device.

---

## 1. Packages Wobble recommends

| Tool | Termux package | Installs | Verified in |
|:---|:---|:---|:---|
| Git | `git` | `git` | `packages/git/build.sh` |
| Python 3 | `python` | `python3`, `pip` | `packages/python/build.sh` |
| Node.js + npm | `nodejs` | `node`, `npm`, `npx` | `packages/nodejs/build.sh` |
| PHP | `php` | `php` | `packages/php/build.sh` |
| JDK 17 | `openjdk-17` | `java`, `javac`, `keytool`, … | `packages/openjdk-17/build.sh` (`TERMUX_PKG_VERSION=17.0.x`) |
| JDK 21 / 25 | `openjdk-21`, `openjdk-25` | same, via `update-alternatives` | `packages/openjdk-21/build.sh`, `packages/openjdk-25/build.sh` |
| Gradle | `gradle` | `gradle` (9.8.2 at verification time) | `packages/gradle/build.sh` |
| aapt + zipalign | `aapt` | `aapt`, `zipalign`, `aidl` | `packages/aapt/build.sh`; `vendor/CMakeLists.txt` in [`termux/android-build-tools`](https://github.com/termux/android-build-tools) installs `zipalign` |
| aapt2 | `aapt2` | `aapt2` | split package declared in `packages/aapt/aapt2.subpackage.sh` (`TERMUX_SUBPKG_INCLUDE="bin/aapt2"`) |
| apksigner | `apksigner` | `apksigner` wrapper + JAR (depends on `openjdk-21`) | `packages/apksigner/build.sh` |
| ADB / fastboot | `android-tools` | `adb`, `fastboot`, … | `packages/android-tools/build.sh` |
| termux-open / am | `termux-tools` | `termux-open`, `termux-setup-storage`, and `termux-am` (dependency) | `packages/termux-tools/build.sh` |
| zip/unzip | `zip`, `unzip` | — | `packages/zip/build.sh`, `packages/unzip/build.sh` |

Consequences that Wobble now reflects:

* Installing **`aapt apksigner` alone does not provide `aapt2`** — the split
  package must be requested explicitly. The doctor hint is therefore
  `pkg install -y aapt aapt2 apksigner`.
* `zipalign` is **not** a standalone package; it comes with `aapt`.
* `apksigner` pulls in **`openjdk-21`**, which becomes the default `java` through
  `update-alternatives`. A project that needs JDK 17 can switch back with
  `update-alternatives --config java`.

---

## 2. Names that do *not* exist (and what to use instead)

| Wrong | Why | Use instead |
|:---|:---|:---|
| `openjdk-11` | Termux has never packaged OpenJDK 11. | `openjdk-17` (or `openjdk-21`/`openjdk-25` for Gradle-only work). |
| `openjdk17` | Package names use a hyphen before the major version. | `openjdk-17` |
| `zipalign` | Ships inside `aapt`. | `pkg install -y aapt` |
| `android-sdk`, `android-build-tools` | No such Termux package; the SDK is not distributable through the repo. | Google's command-line tools + `sdkmanager` (see below). |
| `termux-open` | A binary, not a package. | `pkg install -y termux-tools` |
| `adbs`/`adb` | `adb` is a binary. | `pkg install -y android-tools` |

"Package not found" on Termux is usually a stale index or a mirror problem, not
a missing package. Run `pkg update` (and `termux-change-repo` if the mirror is
unreachable) before concluding that a package does not exist.

---

## 3. Android SDK

No Termux package and no mainstream Linux distribution provides the Android SDK.
It must come from Google:

```bash
# commandline-tools extracted to ~/android-sdk/cmdline-tools/latest
export ANDROID_HOME="$HOME/android-sdk"
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

`wob deps install android-sdk` runs exactly this once `sdkmanager` is on `PATH`,
and `wob doctor` reports the detected platforms/build-tools.

---

## 4. Linux distributions

Wobble also runs outside Termux, where `pkg` does not exist. The mapping used for
install hints is:

| Tool key | Termux | Debian/Ubuntu (`apt`) | Fedora (`dnf`) | Arch (`pacman`) |
|:---|:---|:---|:---|:---|
| JDK 17 | `openjdk-17` | `openjdk-17-jdk` | `java-17-openjdk-devel` | `jdk17-openjdk` |
| Python | `python` | `python3`, `python3-pip` | `python3`, `python3-pip` | `python`, `python-pip` |
| Node.js | `nodejs` | `nodejs`, `npm` | `nodejs`, `npm` | `nodejs`, `npm` |
| PHP | `php` | `php-cli` | `php-cli` | `php` |
| ADB | `android-tools` | `adb` | `android-tools` | `android-tools` |
| Gradle | `gradle` | `gradle` | `gradle` | `gradle` |
| aapt / aapt2 / apksigner | `aapt`, `aapt2`, `apksigner` | *not packaged* → use `sdkmanager` | *not packaged* | *not packaged* |

---

## 5. Re-verifying

```bash
# from a checkout of termux/termux-packages
ls packages/openjdk-17 packages/openjdk-21 packages/aapt packages/apksigner \
   packages/gradle packages/android-tools packages/termux-tools
cat packages/aapt/aapt2.subpackage.sh
pkg search openjdk
pkg search aapt
```

Wobble's own verification test (`tests/test_packages.py`) asserts that every
package name emitted for Termux is one of the verified names above, so a typo
cannot silently reach the doctor output.
