# Android Development on Termux with Wobble

This guide outlines native Android application development inside Termux using Wobble.

---

## 1. Prerequisites (verified package names)

Run the package-index update first. A stale index is the most common reason `pkg`
reports a package as unavailable:

```bash
pkg update
```

| Tool | Install | Notes |
|:---|:---|:---|
| OpenJDK 17 | `pkg install -y openjdk-17` | Termux also packages `openjdk-21` and `openjdk-25`. There is no `openjdk-11` package. The Android Gradle Plugin 8.x needs JDK 17 or newer. |
| AAPT, AAPT2, zipalign | `pkg install -y aapt aapt2` | `aapt` installs `aapt` **and** `zipalign`; `aapt2` is a split package of the same Android build-tools tree. |
| apksigner | `pkg install -y apksigner` | Separate package; it depends on `openjdk-21`. |
| Gradle | `pkg install -y gradle` | Termux currently ships Gradle 9.8.2. See the wrapper note in §3 before building. |
| Android SDK | *not packaged* | Termux and Linux distributions do not ship the SDK. Install Google's command-line tools and use `sdkmanager` (see §2). |
| ADB (optional) | `pkg install -y android-tools` | Only needed for `wob apk install --method adb`. |

`wob doctor` prints the correct command for the package manager it detects
(`pkg` on Termux, `apt`/`dnf`/`pacman` on Linux) and flags tools that no
distribution packages, such as the Android build-tools. The verified package
list lives in [`docs/termux_packages.md`](termux_packages.md).

---

## 2. Install the Android SDK

Termux has no `android-sdk` package, so the SDK comes from Google's
command-line tools:

```bash
# after extracting commandline-tools into ~/android-sdk/cmdline-tools/latest
export ANDROID_HOME="$HOME/android-sdk"
yes | sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"
```

Once `sdkmanager` is on `PATH`, `wob deps install android-sdk` runs the same
install for you and `wob doctor` reports the detected platforms and build-tools.

---

## 3. Project creation

```bash
wob create android mycalculator --package com.example.calculator
```

This generates a minimal Android project:

```
mycalculator/
├── wobble.json                  # Machine-readable spec
├── build.gradle                 # Root build script (AGP 8.13.2)
├── settings.gradle              # Module inclusion
├── gradle.properties            # Memory & daemon optimisations for Termux
├── gradle/wrapper/gradle-wrapper.properties   # Pins Gradle 8.13
└── app/
    ├── build.gradle             # App module build script (compileSdk 34)
    └── src/main/
        ├── AndroidManifest.xml  # App manifest
        ├── java/com/example/calculator/MainActivity.java
        └── res/
            ├── layout/activity_main.xml
            └── values/strings.xml
```

The scaffold pins **Gradle 8.13** in `gradle-wrapper.properties`, matching the
Android Gradle Plugin 8.13.2 it declares. Wobble does not vendor the Gradle
wrapper JAR (a binary), so `gradlew` itself is generated once by Gradle:

```bash
gradle wrapper --gradle-version 8.13   # run inside the project, once
```

After that, `wob apk build` prefers `./gradlew` and builds with Gradle 8.13 even
if the system Gradle is newer. If you build without the wrapper, Wobble detects
that the installed Gradle cannot run the project's AGP and stops with an
explanation and this exact command instead of a Gradle stack trace.

---

## 4. Building APKs

Inside your project directory:

```bash
wob apk build             # debug build
wob apk build --release   # release build
```

Wobble passes `--no-daemon` and the generated `gradle.properties` caps the JVM
heap at `-Xmx1024m` and disables parallel workers, which keeps builds inside the
memory budget of a phone and avoids Android's phantom-process killer.

---

## 5. Inspecting generated APKs

Wobble includes a built-in APK inspector that parses the APK archive directly:

```bash
wob apk info
```

Output:

- Package name and application label
- Version name and version code
- Min SDK and target SDK
- DEX file count and native ABIs (`arm64-v8a`, …)
- SHA-256 checksum and size
- Declared Android permissions

When `aapt`/`aapt2` are installed they are used for exact metadata; otherwise a
pure-Python binary-XML parser provides a best-effort fallback.

---

## 6. Installing the APK on your device

```bash
wob apk install
```

### How installation works without root or ADB

Termux runs as an ordinary Android app, so it cannot install packages silently:

1. Wobble hands the APK to Android through `termux-open` (a broadcast to the
   Termux app's file provider), falling back to an `am start` `ACTION_VIEW`
   intent with MIME type `application/vnd.android.package-archive`.
2. Android opens the system **Package Installer**.
3. You tap **Install** to confirm.

### Installing over ADB

```bash
pkg install -y android-tools
wob apk install --method adb
```

This runs `adb install -r` against whatever device ADB is already connected to.
On a single phone you must first pair/connect your own device, for example via
**Wireless debugging** (`adb pair <ip>:<port>` then `adb connect <ip>:<port>`).
Port `5555` only applies after `adb tcpip 5555` over a USB connection; Android's
wireless-debugging mode picks a random port. Wobble does not guess a port for
you: check `adb devices` first.
