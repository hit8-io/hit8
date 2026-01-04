#!/bin/bash
set -e

# 1. Install without locking issues (Packer guarantees network)
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y squid dante-server iptables-persistent

# 2. Configure Squid
cat > /etc/squid/squid.conf << 'EOF'
acl localnet src 10.0.0.0/8
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443
acl CONNECT method CONNECT
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow localhost manager
http_access deny manager
http_access allow localnet
http_access allow localhost
http_access deny all
http_port 3128
EOF

# 3. Configure Dante (Corrected for GCP Interface Name)
# We use 'ens4' because that is the standard interface name for Debian 12 on GCP e2 instances.
# We also set user.unprivileged to 'nobody' so it drops root privileges safely.

touch /var/log/socks.log
chown nobody:nogroup /var/log/socks.log

cat > /etc/danted.conf << 'DANTE_EOF'
logoutput: /var/log/socks.log

# Internal: Listen on all interfaces
internal: 0.0.0.0 port = 1080

# External: Use the specific interface name (ens4 on GCP)
external: ens4

# Authentication
socksmethod: none
clientmethod: none

# Privileges (Run as nobody for security)
user.privileged: root
user.unprivileged: nobody

# Client Rules (Who can connect?)
client pass {
    from: 0.0.0.0/0 to: 0.0.0.0/0
}

# Socks Rules (Where can they go?)
socks pass {
    from: 0.0.0.0/0 to: 0.0.0.0/0
}
DANTE_EOF


# 4. Enable Services (so they start automatically on boot)
systemctl enable squid danted

# 5. Pre-configure IP Forwarding
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-gcp-nat.conf

# 6. IPTables (We create a loader script because iptables don't persist easily in images)
cat > /etc/network/if-pre-up.d/nat-setup << 'NAT_EOF'
#!/bin/sh
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
NAT_EOF
chmod +x /etc/network/if-pre-up.d/nat-setup
