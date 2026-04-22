FROM python:3.10-slim-bookworm

# 1. Aggiorna i pacchetti e installa il demone SSH e strumenti base che un attaccante si aspetta
RUN apt-get update && apt-get install -y \
    openssh-server \
    sudo \
    curl \
    wget \
    nano \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /var/run/sshd

# 2. Installa la libreria requests per la futura comunicazione con l'MCP Server
RUN pip install --no-cache-dir requests

# 3. Copia lo script della fakeshell nel container
COPY fakeshell.py /usr/local/bin/fakeshell.py
RUN chmod +x /usr/local/bin/fakeshell.py

# 4. Crea l'utente honeypot e imposta la fakeshell
RUN useradd -m -s /usr/local/bin/fakeshell.py honeypot \
    && echo 'honeypot:password123' | chpasswd

# 5. Registra la fakeshell come shell valida per il sistema
RUN echo "/usr/local/bin/fakeshell.py" >> /etc/shells

# 6. Configura SSH per permettere l'accesso tramite password sulla porta 2222
RUN sed -i 's/#Port 22/Port 2222/' /etc/ssh/sshd_config \
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config \
    # Disabilita il MOTD standard di SSH, lo stamperemo noi dalla fakeshell
    && sed -i 's/#PrintMotd yes/PrintMotd no/' /etc/ssh/sshd_config

EXPOSE 2222

# Avvia il demone SSH
CMD ["/usr/sbin/sshd", "-D"]