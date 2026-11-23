#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

for node in spine-01 spine-02 leaf-01 leaf-02 leaf-03 leaf-04 border-01 border-02 wan-rtr-01 wan-rtr-02; do
  mkdir -p "configs/$node"
done

cat > configs/spine-01/frr.conf <<'EOF'
hostname spine-01
! frr defaults
router ospf
 ospf router-id 10.255.0.11
 network 10.0.0.0/8 area 0
!
router bgp 65000
 bgp router-id 10.255.0.11
 neighbor 10.255.0.13 remote-as 65001
 neighbor 10.255.0.14 remote-as 65002
 neighbor 10.255.0.15 remote-as 65003
 neighbor 10.255.0.16 remote-as 65004
 address-family l2vpn evpn
  neighbor 10.255.0.13 activate
  neighbor 10.255.0.14 activate
  neighbor 10.255.0.15 activate
  neighbor 10.255.0.16 activate
 exit-address-family
!
line vty
EOF

cat > configs/spine-02/frr.conf <<'EOF'
hostname spine-02
router ospf
 ospf router-id 10.255.0.12
 network 10.0.0.0/8 area 0
!
router bgp 65000
 bgp router-id 10.255.0.12
 neighbor 10.255.0.13 remote-as 65001
 neighbor 10.255.0.14 remote-as 65002
 neighbor 10.255.0.15 remote-as 65003
 neighbor 10.255.0.16 remote-as 65004
 address-family l2vpn evpn
  neighbor 10.255.0.13 activate
  neighbor 10.255.0.14 activate
  neighbor 10.255.0.15 activate
  neighbor 10.255.0.16 activate
 exit-address-family
!
line vty
EOF

make_leaf() {
  local name=$1 asn=$2 loop=$3
  cat > "configs/$name/frr.conf" <<EOF
hostname $name
router ospf
 ospf router-id $loop
 network 10.0.0.0/8 area 0
!
router bgp $asn
 bgp router-id $loop
 neighbor 10.255.0.11 remote-as 65000
 neighbor 10.255.0.12 remote-as 65000
 address-family l2vpn evpn
  neighbor 10.255.0.11 activate
  neighbor 10.255.0.12 activate
  advertise-all-vni
 exit-address-family
!
vni 10010
 vni 10020
!
line vty
EOF
}
make_leaf leaf-01 65001 10.255.0.13
make_leaf leaf-02 65002 10.255.0.14
make_leaf leaf-03 65003 10.255.0.15
make_leaf leaf-04 65004 10.255.0.16

make_border() {
  local name=$1 loop=$2 wan_as=$3
  cat > "configs/$name/frr.conf" <<EOF
hostname $name
router ospf
 ospf router-id $loop
 network 10.0.0.0/8 area 0
!
router bgp $wan_as
 bgp router-id $loop
 neighbor 10.255.0.11 remote-as 65000
 neighbor 10.255.0.12 remote-as 65000
 address-family l2vpn evpn
  neighbor 10.255.0.11 activate
  neighbor 10.255.0.12 activate
  advertise-all-vni
 exit-address-family
!
line vty
EOF
}
make_border border-01 10.255.0.17 65101
make_border border-02 10.255.0.18 65102

for spec in "wan-rtr-01 65100 10.255.0.19" "wan-rtr-02 65100 10.255.0.20"; do
  set -- $spec
  cat > "configs/$1/frr.conf" <<EOF
hostname $1
router ospf
 ospf router-id $3
 network 10.0.0.0/8 area 0
!
router bgp $2
 bgp router-id $3
 network 10.0.0.0/8
!
line vty
EOF
done

for node in spine-01 spine-02 leaf-01 leaf-02 leaf-03 leaf-04 border-01 border-02 wan-rtr-01 wan-rtr-02; do
  cp configs/daemons "configs/$node/daemons"
done
