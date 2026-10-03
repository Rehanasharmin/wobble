"""
Wobble Android Framework Plugin
Provides native Android project scaffolding, Gradle build coordination, APK packaging, and cleaning.
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from wobble.plugins.base import BasePlugin
from wobble.core.context import find_tool, get_android_sdk_candidates, get_java_home_candidates
from wobble.project.spec import ProjectSpec


class AndroidPlugin(BasePlugin):
    name = "android"
    version = "1.0.0"
    description = "Native Android Gradle application development on Termux"
    category = "android"
    required_system_packages = ["openjdk-17", "aapt"]
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
        classpath 'com.android.tools.build:gradle:8.2.2'
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

task clean(type: Delete) {
    delete rootProject.buildDir
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
    <string name="app_name">{app_name}</string>
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
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.2-bin.zip
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
                "system": ["openjdk-17"],
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
