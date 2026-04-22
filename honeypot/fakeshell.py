#!/usr/bin/env python3
import os
import json
import sys
import tty
import termios
import pty
import shlex
import time
import select
import socket
import getpass
import readline
import glob

LOG_FILE = "/var/log/fakeshell.json"
ip = "192.168.1.150"

# Informazioni utente simulate
user = getpass.getuser()
hostname = socket.gethostname()

# Logging avanzato
def log_command(cmd, cwd):
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ip": ip,
        "user": user,
        "cwd": cwd,
        "cmd": cmd
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

# Ambiente realistico
env = os.environ.copy()
env.update({
    "USER": user,
    "HOME": os.path.expanduser("~"),
    "SHELL": "/bin/bash",
    "TERM": "xterm-256color",
})

home_dir = env["HOME"]
cwd = home_dir

aliases = {
    "ll": "ls -alF",
    "la": "ls -A",
    "l": "ls -CF"
}

# Permette TAB completion
readline.parse_and_bind("tab: complete")

def list_binaries_in_path():
    bins = []
    for p in os.environ.get("PATH", "").split(":"):
        if os.path.isdir(p):
            for f in os.listdir(p):
                full = os.path.join(p, f)
                if os.access(full, os.X_OK) and os.path.isfile(full):
                    bins.append(f)
    return set(bins)

BINARIES = list_binaries_in_path()

def smart_path_completion(text):
    """Restituisce completamenti per path, espandendo ~ e aggiungendo / alle directory."""
    expanded = os.path.expanduser(text)
    matches = glob.glob(expanded + "*")

    results = []
    for m in matches:
        # Ripristina forma originale se necessario
        display = m

        # Aggiungi / se è una directory
        if os.path.isdir(m):
            display += "/"

        results.append(display)

    return results


def completer(text, state):
    buffer = readline.get_line_buffer()
    tokens = buffer.split()

    # Primo token: completa comandi
    if len(tokens) == 1 and not buffer.endswith(" "):
        # Completa comandi del PATH e file eseguibili nella cwd
        candidates = [b for b in BINARIES if b.startswith(text)]

        # Completare anche file eseguibili nella directory corrente
        for f in os.listdir("."):
            if f.startswith(text) and os.access(f, os.X_OK):
                candidates.append(f)

        candidates = sorted(set(candidates))

        try:
            return candidates[state]
        except IndexError:
            return None

    # Se siamo su un argomento → completamento path intelligente
    candidates = smart_path_completion(text)

    try:
        return candidates[state]
    except IndexError:
        return None

# Imposta il completatore
readline.set_completer(completer)
readline.set_completer_delims(" \t\n;")

while True:
    try:
        symbol = "#" if user == "root" else "$"
        prompt = f"\033[1;32m{user}@{hostname}\033[0m:\033[1;34m{cwd}\033[0m{symbol} "
        cmd = input(prompt)
    except EOFError:
        break

    if not cmd.strip():
        continue

    # Alias espansi
    for a, c in aliases.items():
        if cmd.strip().startswith(a + " "):
            cmd = cmd.replace(a, c, 1)
        if cmd.strip() == a:
            cmd = c

    log_command(cmd, cwd)

    if cmd in ["exit", "quit"]:
        print("logout")
        break

    # Gestione cd avanzato
    if cmd.startswith("cd"):
        try:
            parts = shlex.split(cmd)
            if len(parts) < 2 or parts[1] == "~":
                target = home_dir
            elif parts[1] == "-":
                target = os.environ.get("OLDPWD", cwd)
            else:
                target = parts[1]

            new_dir = os.path.abspath(os.path.join(cwd, os.path.expanduser(target)))

            if os.path.isdir(new_dir):
                os.environ["OLDPWD"] = cwd
                cwd = new_dir
            else:
                print(f"cd: {target}: No such file or directory")
        except Exception as e:
            print("cd error:", e)
        continue

    # Esecuzione comandi reali (supporta input interattivo)
    try:
        pid, fd = pty.fork()
        if pid == 0:
            # Child process → esegue il comando
            os.chdir(cwd)
            os.execve("/bin/bash", ["bash", "-c", cmd], env)
        else:
            # Parent → gestisce I/O interattivo
            old_settings = termios.tcgetattr(sys.stdin)

            try:
                tty.setraw(sys.stdin.fileno())

                while True:
                    # Monitoro sia l'output del child sia l'input dell'utente
                    r, _, _ = select.select([fd, sys.stdin], [], [])

                    for s in r:
                        if s == fd:
                            # Output del processo figlio
                            try:
                                output = os.read(fd, 1024)
                                if not output:
                                    raise OSError  # child terminated
                                os.write(sys.stdout.fileno(), output)
                            except OSError:
                                # Il child è terminato
                                raise StopIteration

                        elif s == sys.stdin:
                            # Input dell'utente → inviato al pty del child
                            user_input = os.read(sys.stdin.fileno(), 1024)
                            os.write(fd, user_input)

            except StopIteration:
                pass
            finally:
                # Ripristina il terminale
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    except Exception as e:
        print(f"Error executing command: {str(e)}")
