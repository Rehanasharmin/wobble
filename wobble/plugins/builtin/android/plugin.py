"""
Wobble Android Framework Plugin
Provides native Android project scaffolding, Gradle build coordination, APK packaging, and cleaning.
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.core.context import find_tool, get_android_sdk_candidates, get_java_home_candidates
from wobble.core.executor import run_command
from wobble.project.spec import ProjectSpec


#: Gradle version the scaffold pins in gradle-wrapper.properties.
WRAPPER_GRADLE_VERSION = "8.13"
#: AGP shipped in the scaffold and the minimum Gradle it supports.
SCAFFOLD_AGP = "8.13.2"
MIN_GRADLE_FOR_AGP = (8, 13)


def _parse_version(text: str) -> Optional[tuple]:
    """Extract the first dotted version from tool output."""
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not match:
        return None
    return tuple(int(part) for part in match.groups(default="0")[:3])


def project_agp_version(project_path: Path) -> Optional[tuple]:
    """Read the Android Gradle Plugin version pinned by the project."""
    for name in ("build.gradle", "build.gradle.kts"):
        candidate = project_path / name
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.search(r"com\.android\.tools\.build:gradle:(\d+)\.(\d+)(?:\.(\d+))?", text)
        if match:
            return tuple(int(part) for part in match.groups(default="0")[:3])
    return None


def gradle_compatibility_problem(project_path: Path) -> Optional[Dict[str, str]]:
    """Detect a system Gradle that cannot run the project's AGP.

    The scaffold ships wrapper *properties* but no ``gradlew`` (the wrapper JAR
    is a binary artifact Wobble does not vendor).  When the wrapper is absent,
    ``wob apk build`` falls back to the system ``gradle``; on Termux that is now
    Gradle 9.8.2, while the scaffold's AGP 8.x line targets Gradle 8.13.  Rather
    than letting Gradle print a stack trace, return an actionable diagnosis.
    """
    if (project_path / "gradlew").exists():
        return None
    gradle_bin = find_tool("gradle")
    if not gradle_bin:
        return None
    agp = project_agp_version(project_path)
    if not agp:
        return None
    version_text = ""
    try:
        result = run_command([gradle_bin, "--version"], cwd=project_path, timeout=25)
        version_text = (result.stdout or "") + (result.stderr or "")
    except Exception:
        return None
    gradle = _parse_version(version_text.split("Gradle", 1)[-1]) if "Gradle" in version_text else None
    if not gradle:
        return None

    problem = None
    if agp[0] == 8 and gradle[0] >= 9:
        problem = (f"system Gradle {gradle[0]}.{gradle[1]} cannot run the project's "
                   f"Android Gradle Plugin {agp[0]}.{agp[1]}")
    elif agp[0] == 8 and (gradle[0], gradle[1]) < MIN_GRADLE_FOR_AGP:
        problem = (f"AGP {agp[0]}.{agp[1]} needs Gradle {MIN_GRADLE_FOR_AGP[0]}."
                   f"{MIN_GRADLE_FOR_AGP[1]} or newer, but Gradle {gradle[0]}.{gradle[1]} "
                   "is installed")
    elif agp[0] >= 9 and gradle < (9, 6):
        problem = (f"AGP {agp[0]}.{agp[1]} needs Gradle 9.6 or newer, but Gradle "
                   f"{gradle[0]}.{gradle[1]} is installed")
    if not problem:
        return None
    return {
        "reason": problem,
        "hint": (f"This project pins Gradle {WRAPPER_GRADLE_VERSION} in "
                 "gradle/wrapper/gradle-wrapper.properties. Generate the wrapper once "
                 f"with 'gradle wrapper --gradle-version {WRAPPER_GRADLE_VERSION}', then "
                 "run 'wob apk build' again (./gradlew is used automatically)."),
        "agp": f"{agp[0]}.{agp[1]}.{agp[2]}",
        "gradle": f"{gradle[0]}.{gradle[1]}.{gradle[2]}",
    }


def _xml_escape(value: str) -> str:
    """Escape text for Android XML resources without importing xml.sax."""
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))


class AndroidPlugin(BasePlugin):
    name = "android"
    version = "1.0.0"
    description = "Native Android Gradle application development on Termux"
    category = "android"
    # Verified against termux/termux-packages: aapt ships aapt+zipalign, aapt2 is
    # a split package, apksigner is separate (and pulls openjdk-21).
    required_system_packages = ["openjdk-17", "aapt", "aapt2", "apksigner"]
    required_tools = ["java"]

    def detect(self, project_path: Path) -> bool:
        """Detect whether project is an Android Gradle project."""
        if (project_path / "app" / "build.gradle").exists() or (project_path / "app" / "build.gradle.kts").exists():
            return True
        if (project_path / "AndroidManifest.xml").exists() or (project_path / "app" / "src" / "main" / "AndroidManifest.xml").exists():
            return True
        return False

    def create_project(self, name: str, target_dir: Path, options: Optional[Dict[str, Any]] = None) -> bool:
        """Scaffold a minimal, valid Android Gradle project structure."""
        opts = options or {}
        pkg = opts.get("package") or f"com.example.{name.lower().replace('-', '_')}"
        app_name = opts.get("app_name") or name

        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Root build.gradle
        root_gradle = target_dir / "build.gradle"
        with open(root_gradle, "w", encoding="utf-8") as f:
            f.write("""// Top-level build file where you can add configuration options common to all sub-projects/modules.
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath 'com.android.tools.build:gradle:8.13.2'
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

// layout.buildDirectory replaced the deprecated Project.buildDir accessor,
// which Gradle 9 removed entirely.
tasks.register('clean', Delete) {
    delete rootProject.layout.buildDirectory
}
""")

        # 2. settings.gradle
        settings_gradle = target_dir / "settings.gradle"
        with open(settings_gradle, "w", encoding="utf-8") as f:
            f.write(f"""rootProject.name = "{name}"
include ':app'
""")

        # 3. gradle.properties
        gradle_props = target_dir / "gradle.properties"
        with open(gradle_props, "w", encoding="utf-8") as f:
            f.write("""# Optimization settings for Termux resource constraints
org.gradle.jvmargs=-Xmx1024m -XX:+UseParallelGC -Dfile.encoding=UTF-8
org.gradle.daemon=false
org.gradle.parallel=false
android.useAndroidX=true
""")

        # 4. App module structure
        app_dir = target_dir / "app"
        app_src = app_dir / "src" / "main"
        pkg_rel_path = pkg.replace(".", "/")
        java_src = app_src / "java" / pkg_rel_path
        res_dir = app_src / "res"
        res_layout = res_dir / "layout"
        res_values = res_dir / "values"

        java_src.mkdir(parents=True, exist_ok=True)
        res_layout.mkdir(parents=True, exist_ok=True)
        res_values.mkdir(parents=True, exist_ok=True)

        # 5. app/build.gradle
        app_gradle = app_dir / "build.gradle"
        with open(app_gradle, "w", encoding="utf-8") as f:
            f.write(f"""plugins {{
    id 'com.android.application'
}}

android {{
    namespace '{pkg}'
    compileSdk 34

    defaultConfig {{
        applicationId '{pkg}'
        minSdk 24
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }}

    buildTypes {{
        release {{
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }}
    }}
    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }}
}}

dependencies {{
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.11.0'
}}
""")

        # 6. AndroidManifest.xml
        manifest = app_src / "AndroidManifest.xml"
        with open(manifest, "w", encoding="utf-8") as f:
            f.write(f"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <application
        android:allowBackup="true"
        android:icon="@android:drawable/sym_def_app_icon"
        android:label="@string/app_name"
        android:roundIcon="@android:drawable/sym_def_app_icon"
        android:supportsRtl="true"
        android:theme="@style/Theme.AppCompat.Light.DarkActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>

</manifest>
""")

        # 7. MainActivity.java
        main_activity = java_src / "MainActivity.java"
        with open(main_activity, "w", encoding="utf-8") as f:
            f.write(f"""package {pkg};

import android.os.Bundle;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {{
    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        TextView tv = findViewById(R.id.welcome_text);
        if (tv != null) {{
            tv.setText("Built with Wobble on Termux!");
        }}
    }}
}}
""")

        # 8. activity_main.xml
        layout_main = res_layout / "activity_main.xml"
        with open(layout_main, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:gravity="center"
    android:padding="24dp">

    <TextView
        android:id="@+id/welcome_text"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="Welcome to Wobble!"
        android:textSize="20sp"
        android:textStyle="bold" />

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_marginTop="12dp"
        android:text="Native Android development running on Termux."
        android:textSize="14sp" />

</LinearLayout>
""")

        # 9. strings.xml
        strings_xml = res_values / "strings.xml"
        with open(strings_xml, "w", encoding="utf-8") as f:
            f.write(f"""<resources>
    <string name="app_name">{_xml_escape(app_name)}</string>
</resources>
""")

        # 10. .gitignore
        gitignore = target_dir / ".gitignore"
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write("""*.iml
.gradle/
/local.properties
/.idea/
.DS_Store
/build/
/captures/
.externalNativeBuild/
.cxx/
*.apk
""")

        # 11. gradle/wrapper/gradle-wrapper.properties
        wrapper_dir = target_dir / "gradle" / "wrapper"
        wrapper_dir.mkdir(parents=True, exist_ok=True)
        wrapper_props = wrapper_dir / "gradle-wrapper.properties"
        with open(wrapper_props, "w", encoding="utf-8") as f:
            f.write("""distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.13-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
""")

        # 10. Write wobble.json spec
        spec = ProjectSpec(
            name=name,
            project_type="android",
            framework="android",
            path=target_dir,
            description="Native Android project created with Wobble",
            package_id=pkg,
            scripts={
                "build": "wob android build",
                "clean": "wob android clean",
                "apk": "wob apk info",
                "install": "wob apk install"
            },
            dependencies={
                "system": ["openjdk-17", "aapt", "aapt2", "apksigner"],
                "project": {"compileSdk": 34, "minSdk": 24}
            }
        )
        spec.save()
        return True

    def get_build_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        opts = options or {}
        is_release = opts.get("release", False)
        target_task = "assembleRelease" if is_release else "assembleDebug"

        # Check for gradlew first
        gradlew = project_path / "gradlew"
        if gradlew.exists() and os.access(gradlew, os.X_OK):
            return ["./gradlew", target_task, "--no-daemon"]
        elif gradlew.exists():
            return ["sh", "./gradlew", target_task, "--no-daemon"]

        # Fallback to system gradle
        gradle_bin = find_tool("gradle")
        if gradle_bin:
            return [gradle_bin, target_task, "--no-daemon"]

        return ["gradle", target_task, "--no-daemon"]

    def get_clean_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        gradlew = project_path / "gradlew"
        if gradlew.exists():
            return ["sh", "./gradlew", "clean", "--no-daemon"]
        gradle_bin = find_tool("gradle")
        if gradle_bin:
            return [gradle_bin, "clean", "--no-daemon"]
        return ["gradle", "clean", "--no-daemon"]

    def get_test_command(self, project_path: Path, options: Optional[Dict[str, Any]] = None) -> Optional[List[str]]:
        gradlew = project_path / "gradlew"
        if gradlew.exists():
            return ["sh", "./gradlew", "test", "--no-daemon"]
        return ["gradle", "test", "--no-daemon"]
