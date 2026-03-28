FROM python:3.11-slim

ARG CLAUDE_CODE_VERSION=latest

RUN apt-get update && \
    for i in 1 2 3; do \
    apt-get install -y --no-install-recommends \
    build-essential git procps sudo curl zsh gh postgresql-client \
    vim locales nodejs npm \
    && break || { echo "Retry $i..."; sleep 5; apt-get update; }; \
    done && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen en_US.UTF-8

ARG USERNAME=vscode
ARG GROUPNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd -g $USER_GID $USERNAME \
    && useradd -m -u $USER_UID -g $USER_GID -d /home/$USERNAME -s /bin/bash $USERNAME

RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R $USER_UID:$USER_GID /commandhistory \
    && echo $SNIPPET >> /home/$USERNAME/.bashrc

RUN mkdir -p /usr/local/share/npm-global && \
    chown -R $USER_UID:$USER_GID /usr/local/share
ENV NPM_CONFIG_PREFIX=/usr/local/share/npm-global
ENV PATH=$PATH:/usr/local/share/npm-global/bin

RUN mkdir -p /workspace /home/$USERNAME/.claude && \
    chown -R $USER_UID:$USER_GID /workspace /home/$USERNAME/.claude

USER $USERNAME

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH=/home/$USERNAME/.local/bin:$PATH

RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}
