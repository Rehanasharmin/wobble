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
                "description": "Include tracebacks and exception-type diagnostics on failures",
                "type": "boolean",
                "default": False
            }
        ],
        "error_handling": {
            "json_failure_contract": {
                "required_fields": {
                    "success": False,
                    "error": "Human-readable, actionable failure message",
                    "error_code": "Stable machine-readable error identifier"
                },
                "optional_fields": ["hint", "details", "warnings", "errors", "stdout", "stderr", "returncode"],
                "example": {
                    "success": False,
                    "error": "Port 3000 is already in use on 127.0.0.1.",
                    "error_code": "port_in_use",
                    "hint": "Stop the other server or try 'wob web preview --port 3001'."
                }
            },
            "exit_codes": {
                "0": "Success (or a clean cancellation where documented)",
                "1": "Command, validation, filesystem, or unexpected runtime failure",
                "2": "Invalid command-line arguments or invalid configuration value",
                "124": "External command timed out (when propagated by the command)",
                "126": "Executable exists but cannot be executed (when propagated)",
                "121": "The installed Wobble runtime could not be loaded (launcher auto-recovers once)",
                "127": "Required executable was not found (when propagated)",
                "130": "Interrupted by Ctrl+C"
            },
            "guarantees": [
                "Malformed arguments honor --json and never emit a Python traceback by default",
                "A non-zero command result has a structured error or failure result",
                "Child process output is captured rather than mixed into JSON documents",
                "Expected errors include recovery hints when a useful remedy is known",
                "Use --verbose for tracebacks and exception type diagnostics"
            ]
        },
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
                            {"name": "--host", "type": "string", "default": "127.0.0.1", "description": "Network interface to bind (localhost by default)"},
                            {"name": "--lan", "type": "boolean", "default": False, "description": "Expose the dev server on the LAN (equivalent to --host 0.0.0.0)"}
                        ]
                    },
                    "build": {
                        "description": "Compile web application for production distribution"
                    },
                    "test": {
                        "description": "Run the project test suite"
                    },
                    "preview": {
                        "description": "Launch the hardened preview server; localhost by default, --lan also prints a LAN URL",
                        "flags": [
                            {"name": "--port", "-p": True, "type": "integer", "description": "Port to serve preview on"},
                            {"name": "--dir", "type": "string", "description": "Directory to serve (defaults to project root or dist/build)"},
                            {"name": "--host", "type": "string", "default": "127.0.0.1", "description": "Network interface to bind"},
                            {"name": "--lan", "type": "boolean", "default": False, "description": "Expose the preview on the LAN (0.0.0.0)"}
                        ]
                    },
                    "serve": {
                        "description": "Serve static build folder via zero-dependency HTTP server",
                        "flags": [
                            {"name": "--port", "-p": True, "type": "integer", "description": "Port to serve on"},
                            {"name": "--host", "type": "string", "default": "127.0.0.1", "description": "Network interface to bind"},
                            {"name": "--lan", "type": "boolean", "default": False, "description": "Expose the server on the LAN (0.0.0.0)"}
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
                "description": "Cached environment health check with regression detection: Android, Termux, storage, memory, SDK, JDK, tools, PATH, and the Wobble installation itself",
                "flags": [
                    {"name": "--json", "type": "boolean", "description": "Return health check as JSON object"},
                    {"name": "--quick", "type": "boolean", "default": False, "description": "Skip subprocess version probes (PATH lookups only)"},
                    {"name": "--only", "type": "string", "description": "Comma-separated categories: system, resources, environment, tools, web, android, wobble"},
                    {"name": "--strict", "type": "boolean", "default": False, "description": "Exit 1 when any check warns or fails (CI-friendly)"},
                    {"name": "--fail-on", "type": "string", "default": "never", "choices": ["never", "warning", "missing", "error"], "description": "Exit 1 at or above this severity"},
                    {"name": "--timings", "type": "boolean", "default": False, "description": "Show per-section timing and probe-cache statistics"},
                    {"name": "--no-cache", "type": "boolean", "default": False, "description": "Ignore and do not write the probe cache"},
                    {"name": "--save-baseline", "type": "boolean", "default": False, "description": "Store this run as the regression baseline"},
                    {"name": "--no-save", "type": "boolean", "default": False, "description": "Do not update the regression baseline"}
                ],
                "result_fields": [
                    "status", "counts", "checks", "regressions", "recovered", "persistent",
                    "timings", "cache", "exit_code"
                ],
                "examples": [
                    "wob doctor",
                    "wob doctor --json --quick",
                    "wob doctor --only android --timings",
                    "wob doctor --fail-on warning"
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
                    {"name": "--all", "type": "boolean", "default": False, "description": "Deep clean including node_modules and Gradle cache"},
                    {"name": "--yes", "type": "boolean", "default": False, "description": "Skip confirmation prompt for destructive cleaning"}
                ]
            },
            "schema": {
                "description": "Print this machine-readable schema for AI coding agent orchestration",
                "flags": []
            },
            "completion": {
                "description": "Generate a shell completion script for bash or zsh",
                "arguments": [
                    {"name": "shell", "type": "string", "required": False, "choices": ["bash", "zsh"], "default": "bash", "description": "Shell to generate a completion script for"}
                ]
            },
            "self": {
                "description": "Inspect, repair, verify, and manage the standalone Wobble installation itself",
                "subcommands": {
                    "status": {
                        "description": "Fast, comprehensive health report: runtime files, bytecode, launcher, PATH, completions, config, disk, and recorded incidents",
                        "flags": [
                            {"name": "--deep", "type": "boolean", "default": False, "description": "Hash every installed file and smoke-test imports"},
                            {"name": "--strict", "type": "boolean", "default": False, "description": "Exit 1 on warnings as well as critical problems"},
                            {"name": "--brief", "type": "boolean", "default": False, "description": "Print a single-line health summary"},
                            {"name": "--root", "type": "string", "description": "Installation root to inspect"},
                            {"name": "--bin", "type": "string", "description": "Launcher directory to inspect"}
                        ],
                        "exit_codes": {"0": "healthy or degraded (unless --strict)", "1": "broken installation"},
                        "result_fields": [
                            "status", "score", "counts", "checks", "issues", "next_steps",
                            "incidents", "timings", "elapsed_ms"
                        ]
                    },
                    "health": {"description": "Alias for self status"},
                    "verify": {
                        "description": "Verify installed files against the manifest with parallel SHA-256 hashing",
                        "flags": [
                            {"name": "--serial", "type": "boolean", "default": False, "description": "Hash sequentially (debugging)"},
                            {"name": "--strict", "type": "boolean", "default": False, "description": "Also fail when the launcher is not executable"}
                        ]
                    },
                    "repair": {
                        "description": "Heal the installation: restore missing or corrupted runtime files from the verified offline snapshot (or the source checkout), rebuild a corrupt manifest, then fix launchers, bytecode, completions, debris, and config",
                        "restores_runtime_files": True,
                        "flags": [
                            {"name": "--restore / --no-restore", "type": "boolean", "default": True, "description": "Restore damaged runtime files (default) or limit repair to metadata fixes"},
                            {"name": "--from", "type": "string", "default": "auto", "choices": ["auto", "snapshot", "source", "network"], "description": "Preferred recovery source"},
                            {"name": "--network", "type": "boolean", "default": False, "description": "Allow downloading a release archive when nothing local works"},
                            {"name": "--url", "type": "string", "description": "Release archive URL for --from network"},
                            {"name": "--emergency", "type": "boolean", "default": False, "description": "Full recovery: restore from any available source, allow downloads, accept a version change"},
                            {"name": "--dry-run", "type": "boolean", "default": False, "description": "Show what would be restored without changing anything"},
                            {"name": "--snapshot", "type": "boolean", "default": False, "description": "Rewrite the offline recovery snapshot from the current runtime"},
                            {"name": "--no-backup", "type": "boolean", "default": False, "description": "Do not keep copies of the damaged files under repair-backups/"},
                            {"name": "--no-compile", "type": "boolean", "default": False, "description": "Skip bytecode compilation"},
                            {"name": "--no-completions", "type": "boolean", "default": False, "description": "Skip shell completions"},
                            {"name": "--no-config", "type": "boolean", "default": False, "description": "Leave config/registry files alone"},
                            {"name": "--path", "type": "boolean", "default": False, "description": "Add the launcher directory to shell startup files"},
                            {"name": "--accept-current", "type": "boolean", "default": False, "description": "Re-baseline manifest hashes after a deliberate local patch (requires --yes when non-interactive)"},
                            {"name": "--yes", "type": "boolean", "default": False, "description": "Skip confirmation for --accept-current"}
                        ],
                        "result_fields": ["success", "repaired", "actions", "failed", "warnings", "unresolved", "verification", "restore", "snapshot", "elapsed_ms"]
                    },
                    "rescue": {
                        "description": "Emergency recovery (alias of `wob rescue`): rebuild the runtime from the offline snapshot, the source checkout, or a release archive even when `wob` cannot start",
                        "flags": [
                            {"name": "--dry-run", "type": "boolean", "default": False, "description": "Show the recovery plan without changing anything"},
                            {"name": "--from", "type": "string", "default": "auto", "choices": ["auto", "snapshot", "source", "network"]},
                            {"name": "--url", "type": "string"},
                            {"name": "--no-backup", "type": "boolean", "default": False}
                        ],
                        "out_of_band": ["<root>/rescue.sh", "<root>/rescue.py", "wob-rescue"]
                    },
                    "watch": {
                        "description": "Continuously re-check installation health and print only changes",
                        "flags": [
                            {"name": "--interval", "type": "number", "default": 2.0, "description": "Seconds between checks (minimum 0.2)"},
                            {"name": "--count", "type": "integer", "default": 0, "description": "Stop after N checks (0 = until Ctrl+C)"},
                            {"name": "--deep", "type": "boolean", "default": False, "description": "Hash files on every tick"}
                        ],
                        "note": "With --json, emits one JSON document per line (NDJSON)"
                    },
                    "incidents": {
                        "description": "Show or clear the failure ledger recorded by crashes and failed repairs",
                        "flags": [
                            {"name": "--limit", "type": "integer", "default": 10},
                            {"name": "--clear", "type": "boolean", "default": False}
                        ]
                    },
                    "install": {
                        "description": "Install a standalone, source-independent copy of Wobble",
                        "flags": [
                            {"name": "--root", "type": "string", "description": "Install directory (default: ~/.local/share/wobble)"},
                            {"name": "--bin", "type": "string", "description": "Launcher directory (default: ~/.local/bin)"},
                            {"name": "--force", "type": "boolean", "default": False, "description": "Replace an existing foreign wob executable"},
                            {"name": "--no-completion", "type": "boolean", "default": False, "description": "Do not install shell completions"},
                            {"name": "--no-path", "type": "boolean", "default": False, "description": "Do not edit shell startup files"},
                            {"name": "--no-snapshot", "type": "boolean", "default": False, "description": "Skip the offline recovery snapshot (loses offline repair)"}
                        ]
                    },
                    "uninstall": {
                        "description": "Remove the installed runtime and launchers (projects are never touched)",
                        "flags": [
                            {"name": "--root", "type": "string", "description": "Install directory"},
                            {"name": "--purge", "type": "boolean", "default": False, "description": "Also remove ~/.wobble and ~/.config/wobble"},
                            {"name": "--yes", "type": "boolean", "default": False, "description": "Skip confirmation"}
                        ]
                    }
                }
            },
            "install": {
                "description": "Alias for `wob self install`: install Wobble as standalone software",
                "flags": [
                    {"name": "--root", "type": "string", "description": "Install directory"},
                    {"name": "--bin", "type": "string", "description": "Launcher directory"},
                    {"name": "--force", "type": "boolean", "default": False},
                    {"name": "--no-completion", "type": "boolean", "default": False},
                    {"name": "--no-path", "type": "boolean", "default": False},
                    {"name": "--no-snapshot", "type": "boolean", "default": False}
                ]
            },
            "rescue": {
                "description": "Alias for `wob self rescue`: emergency recovery of a damaged installation",
                "flags": [
                    {"name": "--dry-run", "type": "boolean", "default": False},
                    {"name": "--from", "type": "string", "default": "auto"},
                    {"name": "--url", "type": "string"},
                    {"name": "--no-backup", "type": "boolean", "default": False},
                    {"name": "--root", "type": "string"},
                    {"name": "--bin", "type": "string"}
                ]
            },
            "uninstall": {
                "description": "Alias for `wob self uninstall`: remove Wobble from this system",
                "flags": [
                    {"name": "--root", "type": "string", "description": "Install directory"},
                    {"name": "--purge", "type": "boolean", "default": False},
                    {"name": "--yes", "type": "boolean", "default": False}
                ]
            },
            "banner": {
                "description": "Print the Wobble ASCII wordmark (also available as JSON)",
                "flags": []
            },
            "about": {
                "description": "Show version, install mode, source independence, architecture, and paths",
                "flags": []
            },
            "version": {
                "description": "Print the Wobble version (same as --version; handled by the fast path)",
                "flags": ["--json"]
            },
            "help": {
                "description": "Show the full help text (same as --help)",
                "flags": []
            },
            "update": {
                "description": "Show the installed version, install mode, and upgrade command",
                "flags": []
            },
            "build": {
                "description": "Build the current project (Android APK or production web bundle)",
                "flags": [
                    {"name": "--release", "type": "boolean", "default": False, "description": "Build a release APK"}
                ]
            },
            "dev": {
                "description": "Start the dev server for the current project (localhost by default)",
                "flags": [
                    {"name": "--port", "-p": True, "type": "integer", "description": "Port to listen on"},
                    {"name": "--host", "type": "string", "default": "127.0.0.1"},
                    {"name": "--lan", "type": "boolean", "default": False, "description": "Expose on LAN"}
                ]
            },
            "preview": {
                "description": "Preview the current project locally, optionally on the LAN",
                "flags": [
                    {"name": "--port", "-p": True, "type": "integer", "description": "Port to listen on"},
                    {"name": "--host", "type": "string", "default": "127.0.0.1"},
                    {"name": "--lan", "type": "boolean", "default": False, "description": "Expose on LAN"}
                ]
            }
        },
        "capabilities": {
            "termux_native": True,
            "root_required": False,
            "adb_required": False,
            "shizuku_required": False,
            "dynamic_path_detection": True,
            "structured_errors": True,
            "json_safe_subprocess_output": True,
            "actionable_error_hints": True,
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
            "lan_ip_detection": True,
            "standalone_install": True,
            "source_independent_runtime": True,
            "self_health_checks": {
                "fast_metadata_scan": True,
                "deep_hash_verification": True,
                "import_smoke_test": True,
                "stable_check_codes": True,
                "exit_code_on_breakage": True,
                "auto_repair": ["runtime_files_from_verified_snapshot", "launchers",
                                "bytecode", "completions", "install_debris",
                                "corrupt_config", "shell_path", "manifest_rebuild"],
                "offline_recovery_snapshot": True,
                "recovery_sources": ["snapshot", "source_checkout", "release_archive"],
                "out_of_band_rescue": ["rescue.py", "rescue.sh", "wob-rescue"],
                "keeps_damaged_files": "repair-backups/",
                "launcher_auto_recovery": True
            },
            "regression_detection": {
                "doctor_snapshots": True,
                "regressions": True,
                "recoveries": True,
                "persistent_failures": True
            },
            "incident_ledger": True,
            "probe_cache": {
                "persisted": True,
                "self_invalidating": True,
                "default_ttl_seconds": 3600
            },
            "preview_security": {
                "localhost_default": True,
                "dotfiles_blocked": True,
                "secret_files_blocked": True,
                "directory_listing": False,
                "symlink_escape_blocked": True,
                "gzip": True
            },
            "installer": {
                "manifest": "install.json",
                "default_root": "~/.local/share/wobble",
                "default_launcher": "~/.local/bin/wob",
                "precompiled_bytecode": True,
                "recovery_snapshot": "snapshot/",
                "rescue_scripts": ["rescue.py", "rescue.sh"],
                "repair_backups": "repair-backups/"
            }
        },
        "environment": get_full_environment_report()
    }
