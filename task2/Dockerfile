# Unified P4 SDN env: BMv2 + p4c + Mininet must share one OS/Python stack.
FROM p4lang/p4c:latest

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ethtool \
        iproute2 \
        iputils-ping \
        isc-dhcp-client \
        iptables \
        libboost-iostreams1.71.0 \
        mininet \
        net-tools \
        openvswitch-switch \
        sudo \
        tcpdump \
        tcpreplay \
        make \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Python deps from monorepo requirements.txt (build context = repo root).
# Also kept at /opt/requirements.txt for entrypoint fallback when /repo is not mounted.
COPY requirements.txt /opt/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir -r /opt/requirements.txt \
        mininet==2.3.0.dev6 \
        psutil \
        "protobuf>=3.19,<4"

# grpcio installs site-packages/google/__init__.py — remove so google.protobuf works.
RUN bash -ec 'rm -f /usr/local/lib/python3.*/site-packages/google/__init__.py; \
    rm -rf /usr/local/lib/python3.*/site-packages/google/__pycache__'

COPY task2/scripts/docker_entrypoint.sh /usr/local/bin/docker_entrypoint.sh
RUN chmod +x /usr/local/bin/docker_entrypoint.sh

WORKDIR /p4

ENTRYPOINT ["/usr/local/bin/docker_entrypoint.sh"]
CMD ["tail", "-f", "/dev/null"]
