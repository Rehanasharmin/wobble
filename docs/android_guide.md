# Android Development on Termux with Wobble

This guide outlines native Android application development inside Termux using Wobble.

---

## 1. Prerequisites

To build native Android applications on Termux, you need:
- **OpenJDK 17**: `pkg install -y openjdk-17`
- **Native Android Build Tools**: `pkg install -y aapt apksigner`
- **Gradle**: `pkg install -y gradle`

Run `wob doctor` to verify your toolchain status.

---

## 2. Project Creation

Create an Android project:
```bash
wob create android mycalculator --package com.example.calculator
```

This generates a minimal, Gradle-compliant Android project structure:
```
mycalculator/
├── wobble.json                  # Machine-readable spec
├── build.gradle                 # Root project Gradle configuration
├── settings.gradle              # Module inclusion
├── gradle.properties            # Memory & daemon optimizations for Termux
└── app/
    ├── build.gradle             # App module build script (compileSdk 34)
    └── src/main/
        ├── AndroidManifest.xml  # App manifest
        ├── java/com/example/calculator/MainActivity.java
        └── res/
            ├── layout/activity_main.xml
            └── values/strings.xml
```

---

## 3. Building APKs

Inside your project directory:
```bash
# Debug APK build
wob apk build

# Or release build
wob apk build --release
```

Wobble invokes Gradle with `--no-daemon` and `-Xmx1024m` to safeguard against Android's Phantom Process Killer and Low Memory Killer.

---

## 4. Inspecting Generated APKs

Wobble includes a built-in APK inspector that parses the APK archive directly:
```bash
wob apk info
```
Output:
- Package Name & Application Label
- Version Name and Version Code
- Min SDK & Target SDK
- DEX file count and architecture libraries (`arm64-v8a`)
- SHA-256 Checksum and size
- Declared Android permissions

---

## 5. Installing the APK on Your Device

```bash
wob apk install
```

### How Installation Works Without Root or ADB:
Because Termux runs as a standard Android application without system elevated permissions:
1. Wobble dispatches a system `ACTION_VIEW` intent with the APK URI to Android OS (`termux-open` or `am start`).
2. Android OS immediately opens the system **Package Installer**.
3. You tap **Install** to confirm on your screen.

If you have enabled **Wireless Debugging / ADB** on localhost:
```bash
wob apk install --method adb
```
Wobble will communicate with ADB on `localhost:5555` to install the package directly.
