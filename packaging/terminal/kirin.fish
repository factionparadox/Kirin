# Kirin Linux fish defaults (/etc/fish/conf.d). Override in ~/.config/fish/config.fish.
if status is-interactive
    function fish_greeting
        # Kirin logo and system info; turn off: touch ~/.config/kirin/no-fastfetch
        if not set -q KIRIN_FASTFETCH_SHOWN; and not test -e ~/.config/kirin/no-fastfetch; and type -q fastfetch
            set -gx KIRIN_FASTFETCH_SHOWN 1
            fastfetch
        end
    end
end
