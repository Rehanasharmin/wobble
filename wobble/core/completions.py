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
    cmds="create project android web apk deps doctor plugin config clean self install uninstall rescue banner about version help update schema completion build dev preview"

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
        self)     subcmds="status health verify repair rescue watch incidents install uninstall" ;;
        install)  subcmds="" ;;
        uninstall) subcmds="" ;;
        rescue)    subcmds="" ;;
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
        'create:Create an Android or web project'
        'project:Manage your projects'
        'android:Native Android projects'
        'web:Web development'
        'apk:Build and manage APKs'
        'deps:Install dependencies and toolchains'
        'doctor:Check Termux and the toolchain'
        'plugin:Browse framework templates'
        'config:Read and write settings'
        'clean:Remove build output'
        'self:Check, repair and maintain Wobble'
        'install:Install Wobble as software'
        'uninstall:Remove the installation'
        'rescue:Emergency recovery'
        'update:Check for updates'
        'version:Print the version'
        'help:Show help'
        'banner:Print the wordmark'
        'about:Show version and environment'
        'schema:Print the CLI schema (JSON)'
        'completion:Generate shell completion'
        'build:Build the current project'
        'dev:Run the current project'
        'preview:Preview the current project'
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
        self)     _values 'subcommand' status health verify repair rescue watch incidents install uninstall ;;
        completion) _values 'shell' bash zsh ;;
    esac
}
_wob "$@"
"""

COMPLETIONS = {
    "bash": BASH_COMPLETION,
    "zsh": ZSH_COMPLETION,
}
