"""
Wobble Schema Generator
Outputs machine-readable JSON descriptions of Wobble CLI commands, arguments, capabilities, and plugins.
Enables AI coding agents to dynamically introspect, validate, and invoke Wobble commands.
"""

from typing import Dict, Any
from wobble import __version__
from wobble.core.context import get_full_environment_report


def get_cli_schema() -> Dict[str, Any]:
    """Return the complete machine-readable Wobble schema."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Wobble CLI Specification",
        "description": "Production-ready Termux development harness CLI and agent capability schema.",
        "version": __version__,
        "command": "wob",
        "global_flags": [
            {
                "name": "--json",
                "description": "Output response as structured JSON instead of human-readable text",
                "type": "boolean",
                "default": False
            },
            {
                "name": "--no-color",
                "description": "Disable ANSI color formatting in terminal output",
                "type": "boolean",
                "default": False
            },
            {
                "name": "--verbose",
                "-v": True,
                "description": "Enable verbose execution logging",
                "type": "boolean",
                "default": False
            }
        ],
        "commands": {
            "create": {
                "description": "Create a new Android or Web project from built-in or plugin templates",
                "arguments": [
                    {
                        "name": "type",
                        "type": "string",
                        "required": True,
                        "choices": ["android", "web"],
                        "description": "Project archetype to scaffold"
                    },
                    {
                        "name": "name",
                        "type": "string",
                        "required": True,
                        "description": "Project name / directory name"
                    }
                ],
                "flags": [
                    {
                        "name": "--framework",
                        "-f": True,
                        "type": "string",
                        "description": "Framework template (e.g. vite, react, vue, svelte, nextjs, python, php, static, basic)",
                        "default": "auto"
                    },
                    {
                        "name": "--package",
                        "-p": True,
                        "type": "string",
                        "description": "Android application package ID (e.g. com.example.myapp)",
                        "default": "com.example.<name>"
                    },
                    {
                        "name": "--dir",
                        "-d": True,
                        "type": "string",
                        "description": "Destination directory path (defaults to current directory / name)"
                    }
                ],
                "examples": [
                    "wob create android myapp",
                    "wob create android myapp --package com.myorg.app",
                    "wob create web mysite",
                    "wob create web myreact --framework react",
                    "wob create web myflask --framework python"
                ]
            },
            "project": {
                "description": "Inspect, list, and manage projects in the current workspace or registered directory",
                "subcommands": {
                    "list": {
                        "description": "List all detected projects in the current directory or workspace",
                        "flags": [
                            {"name": "--path", "type": "string", "description": "Search directory path"}
                        ]
                    },
                    "info": {
                        "description": "Display structured details of the current or specified project",
                        "flags": [
                            {"name": "--path", "type": "string", "description": "Path to project root"}
                        ]
                    },
                    "open": {
                        "description": "Open or navigate to a project directory and display quick-action commands",
                        "arguments": [
                            {"name": "name", "type": "string", "required": True, "description": "Project name or path"}
                        ]
                    },
                    "remove": {
                        "description": "Unregister a project from the registry",
                        "arguments": [
                            {"name": "name", "type": "string", "required": True, "description": "Project name to remove"}
                        ]
                    }
                }
            },
            "android": {
                "description": "Manage and build native Android projects inside Termux",
                "subcommands": {
                    "build": {
                        "description": "Compile Android application into APK using Gradle",
                        "flags": [
                            {"name": "--release", "type": "boolean", "default": False, "description": "Build release APK instead of debug"},
                            {"name": "--clean", "type": "boolean", "default": False, "description": "Run gradle clean before compiling"}
                        ]
                    },
                    "clean": {
                        "description": "Remove build directories and Gradle caches for the Android project"
                    },
                    "info": {
                        "description": "Display Android project configuration, SDK versions, and Gradle setup"
                    },
                    "limitations": {
                        "description": "Report Android OS & Termux security limitations, workarounds, and best practices"
                    }
                }
            },
            "web": {
                "description": "Develop, build, test, and preview web applications",
                "subcommands": {
                    "dev": {
                        "description": "Start the project framework development server (e.g. vite dev, npm run dev, flask run)",
                        "flags": [
                            {"name": "--port", "-p": True, "type": "integer", "description": "Port number to listen on"},
                            {"name": "--host", "type": "string", "default": "0.0.0.0", "description": "Network interface to bind"}
                        ]
                    },
                    "build": {
                        "description": "Compile web application for production distribution"
                    },
                    "test": {
                        "description": "Run the project test suite"
                    },
                    "preview": {
                        "description": "Launch local development preview server and display both localhost and LAN URLs for phone/multi-device testing",
                        "flags": [
                            {"name": "--port", "-p": True, "type": "integer", "description": "Port to serve preview on"},
                            {"name": "--dir", "type": "string", "description": "Directory to serve (defaults to project root or dist/build)"}
                        ]
                    },
                    "serve": {
                        "description": "Serve static build folder via zero-dependency HTTP server",
                        "flags": [
                            {"name": "--port", "-p": True, "type": "integer", "description": "Port to serve on"}
                        ]
                    }
                }
            },
            "apk": {
                "description": "Manage, inspect, locate, build, and install Android APKs",
                "subcommands": {
                    "build": {
                        "description": "Shortcut to build APK for current project",
                        "flags": [
                            {"name": "--release", "type": "boolean", "default": False, "description": "Build release APK"}
                        ]
                    },
                    "list": {
                        "description": "Find and list all generated APK files in the project or workspace",
                        "flags": [
                            {"name": "--path", "type": "string", "description": "Directory to scan for APKs"}
                        ]
                    },
                    "info": {
                        "description": "Inspect and parse APK details (Package ID, Version, Min/Target SDK, Permissions, Signatures, Size)",
                        "arguments": [
                            {"name": "file", "type": "string", "required": False, "description": "Path to .apk file (auto-detects if omitted)"}
                        ]
                    },
                    "install": {
                        "description": "Safely trigger APK installation on Android without assuming root or ADB (uses termux-open, am start, or adb)",
                        "arguments": [
                            {"name": "file", "type": "string", "required": False, "description": "Path to .apk file"}
                        ],
                        "flags": [
                            {"name": "--method", "type": "string", "choices": ["auto", "termux-open", "am", "adb"], "default": "auto", "description": "Installation mechanism"}
                        ]
                    },
                    "share": {
                        "description": "Export APK to Android shared storage / Downloads folder for easy access in Android Files app",
                        "arguments": [
                            {"name": "file", "type": "string", "required": False, "description": "Path to .apk file"}
                        ],
                        "flags": [
                            {"name": "--dest", "type": "string", "description": "Destination directory path"}
                        ]
                    },
                    "sign": {
                        "description": "Sign APK using apksigner and debug or user keystore",
                        "arguments": [
                            {"name": "file", "type": "string", "required": False, "description": "Path to .apk file"}
                        ],
                        "flags": [
                            {"name": "--keystore", "type": "string", "description": "Path to keystore file"},
                            {"name": "--alias", "type": "string", "description": "Key alias"}
                        ]
                    },
                    "clean": {
                        "description": "Remove all generated APK files in the project"
                    }
                }
            },
            "deps": {
                "description": "Unified dependency management across Termux, Android SDK, Node, Python, and PHP",
                "subcommands": {
                    "install": {
                        "description": "Install project dependencies based on detected project type or install specific stack (e.g. wob deps install android-sdk)",
                        "arguments": [
                            {"name": "target", "type": "string", "required": False, "description": "Target stack or blank for current project"}
                        ]
                    },
                    "add": {
                        "description": "Add a package to the current project or system",
                        "arguments": [
                            {"name": "package", "type": "string", "required": True, "description": "Package name to add"}
                        ],
                        "flags": [
                            {"name": "--manager", "-m": True, "type": "string", "choices": ["auto", "termux", "npm", "pip", "composer"], "default": "auto"}
                        ]
                    },
                    "remove": {
                        "description": "Remove a dependency from project or system",
                        "arguments": [
                            {"name": "package", "type": "string", "required": True, "description": "Package name to remove"}
                        ],
                        "flags": [
                            {"name": "--manager", "-m": True, "type": "string", "choices": ["auto", "termux", "npm", "pip", "composer"], "default": "auto"}
                        ]
                    },
                    "doctor": {
                        "description": "Check for missing or broken dependencies for the current project or global toolchain"
                    },
                    "list": {
                        "description": "List declared project dependencies and system packages"
                    }
                }
            },
            "doctor": {
                "description": "Comprehensive environment health check (Android, Termux, storage, memory, SDK, JDK, tools, PATH)",
                "flags": [
                    {"name": "--json", "type": "boolean", "description": "Return health check as JSON object"}
                ]
            },
            "plugin": {
                "description": "Discover, list, inspect, and manage framework plugins",
                "subcommands": {
                    "list": {
                        "description": "List all active, built-in, and custom installed plugins"
                    },
                    "info": {
                        "description": "Show detailed specifications for a specific plugin",
                        "arguments": [
                            {"name": "name", "type": "string", "required": True, "description": "Plugin name"}
                        ]
                    }
                }
            },
            "config": {
                "description": "View and manage Wobble persistent configuration settings",
                "subcommands": {
                    "list": {"description": "List all configuration keys and values"},
                    "get": {
                        "description": "Get value of a configuration key",
                        "arguments": [{"name": "key", "type": "string", "required": True}]
                    },
                    "set": {
                        "description": "Set value for a configuration key",
                        "arguments": [
                            {"name": "key", "type": "string", "required": True},
                            {"name": "value", "type": "string", "required": True}
                        ]
                    }
                }
            },
            "clean": {
                "description": "Clean temporary files, build caches, and node_modules / gradle caches across projects",
                "flags": [
                    {"name": "--all", "type": "boolean", "default": False, "description": "Deep clean including node_modules and Gradle cache"}
                ]
            },
            "schema": {
                "description": "Print this machine-readable schema for AI coding agent orchestration",
                "flags": []
            }
        },
        "capabilities": {
            "termux_native": True,
            "root_required": False,
            "adb_required": False,
            "shizuku_required": False,
            "dynamic_path_detection": True,
            "supported_frameworks": [
                "android", "vite", "react", "vue", "svelte", "nextjs", "python_web", "php", "static_web"
            ],
            "supported_package_managers": [
                "pkg", "apt", "npm", "pnpm", "yarn", "pip", "composer", "sdkmanager"
            ],
            "apk_management": {
                "direct_parsing": True,
                "aapt_support": True,
                "install_methods": ["termux-open", "am", "adb"]
            },
            "lan_ip_detection": True
        },
        "environment": get_full_environment_report()
    }
