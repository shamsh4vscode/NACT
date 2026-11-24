FROM frrouting/frr:latest

RUN apk add --no-cache openssh-server \
    && mkdir -p /root/.ssh \
    && mkdir -p /run/nact \
    && chmod 700 /root/.ssh

COPY sshd_config /etc/ssh/sshd_config
