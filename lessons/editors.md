# Learn Vim and Neovim

Both editors are included in Kirin. Start with their real interactive tutorials:

    kirin-learn tutor vim
    kirin-learn tutor neovim

The Vim command opens `vimtutor`. Neovim opens Kirin's custom `:Tutor kirin-01-basics` lesson. Within Neovim, `:Tutor` opens the upstream beginner lesson.

**Exercise:** Create `/tmp/kirin-notes.txt` with either editor. Use `i` to type, `<Esc>` to return to Normal mode, `:w` to save and `:q` to exit. Check its contents using `cat /tmp/kirin-notes.txt`.

No lesson overwrites your `~/.vimrc` or `~/.config/nvim/init.lua`. More references: `man vim`, `man nvim`, `:help user-manual`.
