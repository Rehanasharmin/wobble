"""
Shell completion scripts for Wobble (bash + zsh).

Kept in its own module so the installer can write completion files without
importing the argument parser.
"""

BASH_COMPLETION = r"""# Wobble (wob) bash completion
# Installed automatically by `wob self install`.
_wob_completions() {
    local cur prev cmds subcmds
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    cmds="create project android web apk deps doctor plugin config clean self install uninstall banner about version help update schema completion build dev preview"

    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "$cmds" -- "$cur") )
        return 0
    fi

    case "${COMP_WORDS[1]}" in
        create)   subcmds="android web" ;;
        project)  subcmds="list info open remove" ;;
        android)  subcmds="build clean info limitations" ;;
        web)      subcmds="dev build test preview serve" ;;
        apk)      subcmds="build list info install share sign clean" ;;
        deps)     subcmds="install add remove doctor list" ;;
        plugin)   subcmds="list info" ;;
        config)   subcmds="list get set" ;;
        self)     subcmds="status verify install uninstall" ;;
        install)  subcmds="" ;;
        uninstall) subcmds="" ;;
        completion) subcmds="bash zsh" ;;
        *)        subcmds="" ;;
    esac

    if [ "$COMP_CWORD" -eq 2 ] && [ -n "$subcmds" ]; then
        COMPREPLY=( $(compgen -W "$subcmds" -- "$cur") )
        return 0
    fi

    case "$prev" in
        -f|--framework) COMPREPLY=( $(compgen -W "vite react vue svelte nextjs python php static" -- "$cur") ) ;;
        --method)       COMPREPLY=( $(compgen -W "auto termux-open am adb" -- "$cur") ) ;;
        -m|--manager)   COMPREPLY=( $(compgen -W "auto termux npm pip composer" -- "$cur") ) ;;
        -p|--port|--host|--package|--dir|--dest|--keystore|--alias|--path|--release|--all|--yes)
                        COMPREPLY=( $(compgen -f -- "$cur") ) ;;
    esac
}
complete -F _wob_completions wob
"""

ZSH_COMPLETION = r"""#compdef wob
# Wobble (wob) zsh completion
# Installed automatically by `wob self install` into ~/.local/share/zsh/site-functions.
_wob() {
    local -a cmds
    cmds=(
        'create:Create a new Android or Web project'
        'project:Manage and inspect projects'
        'android:Native Android development'
        'web:Web development workflows'
        'apk:Locate, inspect, build, and install APKs'
        'deps:Unified package and dependency management'
        'doctor:Run comprehensive environment health diagnostics'
        'plugin:List and inspect framework plugins'
        'config:Manage persistent user configuration'
        'clean:Clean temporary caches and build files'
        'self:Install, verify, or uninstall Wobble itself'
        'install:Install Wobble as standalone software'
        'uninstall:Remove the Wobble installation'
        'banner:Print the ASCII wordmark'
        'about:Show version, install path, and environment'
        'version:Print the Wobble version'
        'help:Show the full help text'
        'update:Check for Wobble updates'
        'schema:Output machine-readable CLI schema'
        'completion:Generate shell completion script'
        'build:Intelligent build for current project'
        'dev:Start dev server for current project'
        'preview:Preview current project locally and on LAN'
    )
    if (( CURRENT == 2 )); then
        _describe 'command' cmds
        return
    fi
    case "${words[2]}" in
        create)   _values 'type' android web ;;
        project)  _values 'subcommand' list info open remove ;;
        android)  _values 'subcommand' build clean info limitations ;;
        web)      _values 'subcommand' dev build test preview serve ;;
        apk)      _values 'subcommand' build list info install share sign clean ;;
        deps)     _values 'subcommand' install add remove doctor list ;;
        plugin)   _values 'subcommand' list info ;;
        config)   _values 'subcommand' list get set ;;
        self)     _values 'subcommand' status verify install uninstall ;;
        completion) _values 'shell' bash zsh ;;
    esac
}
_wob "$@"
"""

COMPLETIONS = {
    "bash": BASH_COMPLETION,
    "zsh": ZSH_COMPLETION,
}
