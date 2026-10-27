#!/usr/bin/env python3
"""Welcome to Kirin: a first-login window linking Kirin's learning tools and apps.

Shown once per user by /etc/xdg/autostart/kirin-welcome.desktop (`--autostart`),
and from the menu at any time. English, or Russian when the session is Russian.
Uses GTK 3 when available; otherwise prints the same guide to the terminal.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

APP_DIRS = (Path('/usr/share/applications'), Path('/var/lib/flatpak/exports/share/applications'),
            Path.home() / '.local/share/flatpak/exports/share/applications')
STATE = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'kirin'
DONE = STATE / 'welcome-done'          # seen at least once
ALWAYS = STATE / 'welcome-always'      # user asked to see it at every login
NO_FASTFETCH = STATE / 'no-fastfetch'

# (desktop file, English title, English blurb, Russian title, Russian blurb)
ITEMS = [
    ('kirin-learn.desktop', 'Learn Linux', 'Offline lessons on the terminal, packages, services and storage.',
     'Изучить Linux', 'Офлайн-уроки: терминал, пакеты, службы и хранилище.'),
    ('kirin-russian-tutor.desktop', 'Russian tutor', 'Practise Russian with a local AI tutor that explains its corrections.',
     'Репетитор русского', 'Практика русского с локальным ИИ-репетитором.'),
    ('kirin-content.desktop', 'Downloads', 'Get the AI models, Russian courses, dictionaries and audiobooks (about 45 GB in all; pick what you want).',
     'Загрузки', 'Модели ИИ, курсы русского, словари и аудиокниги (всего около 45 ГБ; выберите нужное).'),
    ('kirin-russian-path.desktop', 'Russian A1 to B2', 'Your study plan: textbook, courses, words, audiobooks and reading.',
     'Русский: от A1 до B2', 'План занятий: учебник, курсы, слова, аудиокниги и чтение.'),
    ('kirin-russian-library.desktop', 'Russian courses', 'FSI, DLI, Peace Corps and Между нами textbooks and audio.',
     'Курсы русского', 'Учебники и аудио FSI, DLI, Корпуса мира и «Между нами».'),
    ('kirin-russian-dictionary.desktop', 'Dictionary', 'Offline Wiktionary with stress and declension tables.',
     'Словарь', 'Офлайн-Викисловарь с ударениями и таблицами.'),
    ('com.jeffser.Alpaca.desktop', 'AI chat', "Chat with Kirin's local AI models in Alpaca. Nothing leaves this computer.",
     'ИИ-чат', 'Чат с локальными моделями ИИ в Alpaca. Всё остаётся на этом компьютере.'),
    ('io.github.flattool.Warehouse.desktop', 'Get apps', 'Install and manage Flatpak apps with Warehouse.',
     'Приложения', 'Установка и управление приложениями Flatpak в Warehouse.'),
    ('libreoffice-startcenter.desktop', 'Office', 'Documents, spreadsheets and presentations in LibreOffice.',
     'Офис', 'Документы, таблицы и презентации в LibreOffice.'),
    ('kirin-fingerprint.desktop', 'Fingerprint login', 'Enrol a finger to log in, unlock the screen and approve sudo.',
     'Вход по отпечатку', 'Добавьте отпечаток для входа, разблокировки и sudo.'),
    ('ukui-control-center.desktop', 'Settings', 'Language, keyboard, appearance and accounts.',
     'Настройки', 'Язык, клавиатура, оформление и учётные записи.'),
]
TEXT = {
    'en': {'title': 'Welcome to Kirin Linux',
           'intro': 'Kirin works offline: lessons, AI models, Russian courses and the dictionary are all on this computer.',
           'again': 'Show this window when I log in', 'fastfetch': 'Show system info when a terminal opens',
           'close': 'Close', 'open': 'Open'},
    'ru': {'title': 'Добро пожаловать в Kirin Linux',
           'intro': 'Kirin работает без интернета: уроки, модели ИИ, курсы русского и словарь уже на этом компьютере.',
           'again': 'Показывать это окно при входе', 'fastfetch': 'Показывать сведения о системе в терминале',
           'close': 'Закрыть', 'open': 'Открыть'},
}


def language() -> str:
    for var in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(var, '')
        if value:
            return 'ru' if value.split(':')[0].startswith('ru') else 'en'
    return 'en'


def find_desktop(name: str) -> Path | None:
    return next((d / name for d in APP_DIRS if (d / name).is_file()), None)


def available_items(lang: str) -> list[tuple[str, str, str]]:
    out = []
    for desktop, en_t, en_b, ru_t, ru_b in ITEMS:
        if find_desktop(desktop):
            out.append((desktop, ru_t if lang == 'ru' else en_t, ru_b if lang == 'ru' else en_b))
    return out


def set_flag(path: Path, on: bool) -> None:
    if on:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    else:
        path.unlink(missing_ok=True)


def launch(desktop: str) -> None:
    path = find_desktop(desktop)
    if path and shutil.which('gio'):
        subprocess.Popen(['gio', 'launch', str(path)], start_new_session=True)
    elif path and shutil.which('gtk-launch'):
        subprocess.Popen(['gtk-launch', desktop.removesuffix('.desktop')], start_new_session=True)


def run_gtk(lang: str) -> int:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, GdkPixbuf, Gio  # noqa: F401
    t = TEXT[lang]
    win = Gtk.Window(title=t['title'])
    win.set_default_size(640, 560)
    win.set_position(Gtk.WindowPosition.CENTER)
    win.set_icon_name('kirin')
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=24)
    logo = Path('/usr/share/kirin/branding/kirin-logo.png')
    if logo.is_file():
        box.pack_start(Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(logo), 96, 96, True)),
                       False, False, 0)
    heading = Gtk.Label(); heading.set_markup(f'<span size="x-large" weight="bold">{t["title"]}</span>')
    intro = Gtk.Label(label=t['intro']); intro.set_line_wrap(True)
    box.pack_start(heading, False, False, 0)
    box.pack_start(intro, False, False, 0)
    listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    for desktop, title, blurb in available_items(lang):
        row = Gtk.Box(spacing=12, margin=8)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        name = Gtk.Label(xalign=0); name.set_markup(f'<b>{title}</b>')
        info = Gtk.Label(label=blurb, xalign=0); info.set_line_wrap(True)
        labels.pack_start(name, False, False, 0); labels.pack_start(info, False, False, 0)
        button = Gtk.Button(label=t['open'], valign=Gtk.Align.CENTER)
        button.connect('clicked', lambda _b, d=desktop: launch(d))
        row.pack_start(labels, True, True, 0); row.pack_end(button, False, False, 0)
        listbox.add(row)
    scroller = Gtk.ScrolledWindow(); scroller.add(listbox)
    box.pack_start(scroller, True, True, 0)
    again = Gtk.CheckButton(label=t['again']); again.set_active(ALWAYS.exists())
    fetch = Gtk.CheckButton(label=t['fastfetch']); fetch.set_active(not NO_FASTFETCH.exists())
    close = Gtk.Button(label=t['close'])
    box.pack_start(again, False, False, 0); box.pack_start(fetch, False, False, 0)
    box.pack_end(close, False, False, 0)

    def finish(*_):
        set_flag(DONE, True)
        set_flag(ALWAYS, again.get_active())
        set_flag(NO_FASTFETCH, not fetch.get_active())
        Gtk.main_quit()
    close.connect('clicked', finish)
    win.connect('delete-event', finish)
    win.add(box)
    win.show_all()
    Gtk.main()
    return 0


def run_text(lang: str) -> int:
    t = TEXT[lang]
    print(f'{t["title"]}\n\n{t["intro"]}\n')
    for desktop, title, blurb in available_items(lang):
        print(f'  {title}: {blurb}  ({desktop})')
    set_flag(DONE, True)
    return 0


def should_autostart() -> bool:
    return ALWAYS.exists() or not DONE.exists()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--autostart', action='store_true', help='only show if this user has not seen it yet')
    args = ap.parse_args(argv)
    if args.autostart and not should_autostart():
        return 0
    lang = language()
    try:
        return run_gtk(lang)
    except (ImportError, ValueError, RuntimeError):
        return run_text(lang)


if __name__ == '__main__':
    sys.exit(main())
